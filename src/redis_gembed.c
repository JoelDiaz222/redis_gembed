#include "redismodule.h"
#include "gembed.h"

#include <stdlib.h>
#include <string.h>

/* =========================================================================
 * Internal helpers
 * ========================================================================= */

/*
 * resolve_embedder_and_model
 *
 * Validates the embedder name and model name against the Rust library and
 * fills *embedder_id / *model_id.  On any failure it replies with an error
 * to the client and returns REDISMODULE_ERR.
 */
static int resolve_embedder_and_model(RedisModuleCtx *ctx,
                                      const char *embedder_str,
                                      const char *model_str,
                                      int *embedder_id,
                                      int *model_id)
{
    *embedder_id = validate_embedder(embedder_str);
    if (*embedder_id < 0) {
        RedisModule_ReplyWithErrorFormat(ctx,
            "ERR Unknown embedder '%s'", embedder_str);
        return REDISMODULE_ERR;
    }

    *model_id = validate_embedding_model(*embedder_id, model_str,
                                         INPUT_TYPE_TEXT);
    if (*model_id < 0) {
        RedisModule_ReplyWithErrorFormat(ctx,
            "ERR Model '%s' not supported by embedder '%s' for text input",
            model_str, embedder_str);
        return REDISMODULE_ERR;
    }

    return REDISMODULE_OK;
}

/*
 * embed_texts_to_batch
 *
 * Calls the Rust generate_embeddings function for an array of C strings.
 * On success returns REDISMODULE_OK and *batch is populated (caller must
 * call free_embedding_batch).
 * On failure replies with an error to the client and returns REDISMODULE_ERR.
 */
static int embed_texts_to_batch(RedisModuleCtx *ctx,
                                int embedder_id,
                                int model_id,
                                const char **texts,
                                size_t n_texts,
                                EmbeddingBatch *batch)
{
    /* Build StringSlice array (no copies – just pointers into the existing
     * RedisModule string buffers which live for the duration of the call). */
    StringSlice *slices = RedisModule_Alloc(sizeof(StringSlice) * n_texts);
    if (!slices) {
        RedisModule_ReplyWithError(ctx, "ERR out of memory");
        return REDISMODULE_ERR;
    }

    for (size_t i = 0; i < n_texts; i++) {
        slices[i].ptr = texts[i];
        slices[i].len = strlen(texts[i]);
    }

    InputData input = {0};
    input.input_type  = INPUT_TYPE_TEXT;
    input.text_data   = slices;
    input.n_texts     = n_texts;

    memset(batch, 0, sizeof(*batch));
    int rc = generate_embeddings(embedder_id, model_id, &input, batch);
    RedisModule_Free(slices);

    if (rc < 0) {
        RedisModule_ReplyWithErrorFormat(ctx,
            "ERR Embedding generation failed (code=%d)", rc);
        return REDISMODULE_ERR;
    }

    if (batch->n_vectors == 0 || batch->dim == 0 || !batch->data) {
        RedisModule_ReplyWithError(ctx, "ERR Embedding generation returned empty result");
        return REDISMODULE_ERR;
    }

    return REDISMODULE_OK;
}

/* =========================================================================
 * G.EMBED <embedder> <model> <text>
 *
 * Returns one bulk-string: raw IEEE-754 float32 bytes (dim * 4 bytes).
 * ========================================================================= */
static int GembedEmbed_RedisCommand(RedisModuleCtx *ctx,
                                    RedisModuleString **argv,
                                    int argc)
{
    if (argc != 4) {
        return RedisModule_WrongArity(ctx);
    }

    size_t embedder_len, model_len, text_len;
    const char *embedder_str = RedisModule_StringPtrLen(argv[1], &embedder_len);
    const char *model_str    = RedisModule_StringPtrLen(argv[2], &model_len);
    const char *text_str     = RedisModule_StringPtrLen(argv[3], &text_len);

    int embedder_id, model_id;
    if (resolve_embedder_and_model(ctx, embedder_str, model_str,
                                   &embedder_id, &model_id) != REDISMODULE_OK)
        return REDISMODULE_OK; /* error already sent */

    EmbeddingBatch batch;
    const char *texts[1] = { text_str };
    if (embed_texts_to_batch(ctx, embedder_id, model_id,
                             texts, 1, &batch) != REDISMODULE_OK)
        return REDISMODULE_OK; /* error already sent */

    /* Reply with the raw float bytes – compatible with RedisSearch VECTOR field */
    size_t byte_len = batch.dim * sizeof(float);
    RedisModule_ReplyWithStringBuffer(ctx, (const char *)batch.data, byte_len);

    free_embedding_batch(&batch);
    return REDISMODULE_OK;
}

/* =========================================================================
 * G.EMBEDS <embedder> <model> <text> [<text> ...]
 *
 * Returns an array where each element is a raw float32 bulk-string
 * (same format as G.EMBED).
 * ========================================================================= */
static int GembedEmbeds_RedisCommand(RedisModuleCtx *ctx,
                                     RedisModuleString **argv,
                                     int argc)
{
    if (argc < 4) {
        return RedisModule_WrongArity(ctx);
    }

    size_t embedder_len, model_len;
    const char *embedder_str = RedisModule_StringPtrLen(argv[1], &embedder_len);
    const char *model_str    = RedisModule_StringPtrLen(argv[2], &model_len);

    int n_texts      = argc - 3;  /* argv[3..] are the input texts */
    const char **texts = RedisModule_Alloc(sizeof(char *) * n_texts);
    if (!texts) {
        RedisModule_ReplyWithError(ctx, "ERR out of memory");
        return REDISMODULE_OK;
    }

    for (int i = 0; i < n_texts; i++) {
        size_t tlen;
        texts[i] = RedisModule_StringPtrLen(argv[3 + i], &tlen);
    }

    int embedder_id, model_id;
    if (resolve_embedder_and_model(ctx, embedder_str, model_str,
                                   &embedder_id, &model_id) != REDISMODULE_OK) {
        RedisModule_Free(texts);
        return REDISMODULE_OK;
    }

    EmbeddingBatch batch;
    if (embed_texts_to_batch(ctx, embedder_id, model_id,
                             texts, (size_t)n_texts, &batch) != REDISMODULE_OK) {
        RedisModule_Free(texts);
        return REDISMODULE_OK;
    }

    RedisModule_Free(texts);

    /* Validate we got back exactly as many vectors as inputs */
    if (batch.n_vectors != (size_t)n_texts) {
        RedisModule_ReplyWithErrorFormat(ctx,
            "ERR Expected %d embeddings, got %zu", n_texts, batch.n_vectors);
        free_embedding_batch(&batch);
        return REDISMODULE_OK;
    }

    size_t bytes_per_vec = batch.dim * sizeof(float);

    RedisModule_ReplyWithArray(ctx, batch.n_vectors);
    for (size_t i = 0; i < batch.n_vectors; i++) {
        const char *vec_start = (const char *)(batch.data + i * batch.dim);
        RedisModule_ReplyWithStringBuffer(ctx, vec_start, bytes_per_vec);
    }

    free_embedding_batch(&batch);
    return REDISMODULE_OK;
}

/* =========================================================================
 * Module entry point
 * ========================================================================= */
int RedisModule_OnLoad(RedisModuleCtx *ctx,
                       RedisModuleString **argv,
                       int argc)
{
    (void)argv; (void)argc; /* no module-level args used */

    if (RedisModule_Init(ctx, "gembed", 1, REDISMODULE_APIVER_1)
            == REDISMODULE_ERR)
        return REDISMODULE_ERR;

    /* G.EMBED embedder model text → bulk-string */
    if (RedisModule_CreateCommand(ctx,
            "g.embed",
            GembedEmbed_RedisCommand,
            "readonly fast",
            /*first_key=*/0, /*last_key=*/0, /*step=*/0)
            == REDISMODULE_ERR)
        return REDISMODULE_ERR;

    /* G.EMBEDS embedder model text [text ...] → array */
    if (RedisModule_CreateCommand(ctx,
            "g.embeds",
            GembedEmbeds_RedisCommand,
            "readonly fast",
            /*first_key=*/0, /*last_key=*/0, /*step=*/0)
            == REDISMODULE_ERR)
        return REDISMODULE_ERR;

    return REDISMODULE_OK;
}
