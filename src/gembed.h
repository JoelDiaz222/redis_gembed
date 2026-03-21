#ifndef GEMBED_H
#define GEMBED_H

#include <stddef.h>

/* -----------------------------------------------------------------------
 * Input type constants (must match Rust InputType enum repr(C))
 * ----------------------------------------------------------------------- */
#define INPUT_TYPE_TEXT           0
#define INPUT_TYPE_IMAGE          1
#define INPUT_TYPE_MULTIMODAL     2
#define INPUT_TYPE_IMAGE_DIRECTORY 3

/* -----------------------------------------------------------------------
 * C FFI structs (must match #[repr(C)] layout in gembed/src/utils.rs)
 * ----------------------------------------------------------------------- */

/* Flat view of a UTF-8 string — no NUL terminator required */
typedef struct {
    const char *ptr;
    size_t      len;
} StringSlice;

/* Flat view of arbitrary binary data */
typedef struct {
    const unsigned char *ptr;
    size_t               len;
} ByteSlice;

/* Generic embedding input (only text fields used by this module) */
typedef struct {
    int                   input_type;   /* INPUT_TYPE_* */
    const ByteSlice      *binary_data;  /* unused for text */
    size_t                n_binaries;   /* unused for text */
    const StringSlice    *text_data;
    size_t                n_texts;
} InputData;

/* Output of generate_embeddings — flat float buffer owned by Rust */
typedef struct {
    float  *data;       /* row-major: n_vectors × dim floats */
    size_t  n_vectors;
    size_t  dim;
} EmbeddingBatch;

/* -----------------------------------------------------------------------
 * Rust C FFI entry points
 * ----------------------------------------------------------------------- */

/* Returns backend ID (>= 0) on success, negative on failure */
extern int validate_backend(const char *name);

/* Returns model ID (>= 0) on success, negative on failure */
extern int validate_model(int backend_id, const char *model,
                                    int input_type);

/* Fills *out_batch; caller must call free_embedding_batch when done.
 * Returns 0 on success, negative error code on failure. */
extern int generate_embeddings(int backend_id, int model_id,
                               const InputData *input_data,
                               EmbeddingBatch  *out_batch);

/* Releases the float buffer inside *batch (allocated by Rust) */
extern void free_embedding_batch(EmbeddingBatch *batch);

#endif /* GEMBED_H */
