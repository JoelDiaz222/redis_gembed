GEMBED_DIR    = gembed
GEMBED_TARGET = $(GEMBED_DIR)/target/release
GEMBED_LIB    = $(GEMBED_TARGET)/libgembed.a

SRC_DIR       = src
DEPS_DIR      = deps

MODULE_NAME   = redis_gembed
TARGET        = $(MODULE_NAME).so

CC            = gcc
CFLAGS        = -Wall -Wextra -O2 -fPIC \
                -I$(SRC_DIR) \
                -I$(DEPS_DIR)

LDFLAGS       = -shared \
                -L$(GEMBED_TARGET) -lgembed

UNAME_S := $(shell uname -s)

# macOS: modules are bundles with unresolved symbols at link time
ifeq ($(UNAME_S),Darwin)
    LDFLAGS += -undefined dynamic_lookup
endif

# CUDA (optional)
CUDA_LIB_DIR ?= /usr/local/cuda/lib64
ifneq ($(wildcard $(CUDA_LIB_DIR)/.),)
    LDFLAGS += -L$(CUDA_LIB_DIR) -Wl,-rpath,$(CUDA_LIB_DIR) \
               -lcudart -lcuda -lcurand -lcublas
endif

SRCS = $(SRC_DIR)/redis_gembed.c
OBJS = $(SRCS:.c=.o)

.PHONY: all
all: $(TARGET)

$(GEMBED_LIB):
	cd $(GEMBED_DIR) && cargo build --release

$(SRC_DIR)/%.o: $(SRC_DIR)/%.c $(DEPS_DIR)/redismodule.h
	$(CC) $(CFLAGS) -c $< -o $@

$(TARGET): $(GEMBED_LIB) $(OBJS)
	$(CC) $(OBJS) $(LDFLAGS) -o $@

.PHONY: deps
deps: $(DEPS_DIR)/redismodule.h

$(DEPS_DIR)/redismodule.h:
	mkdir -p $(DEPS_DIR)
	curl -fsSL \
	  "https://raw.githubusercontent.com/redis/redis/unstable/src/redismodule.h" \
	  -o $(DEPS_DIR)/redismodule.h

REDIS_CLI := $(shell command -v redis-cli >/dev/null && echo "redis-cli" || echo "valkey-cli")
REDIS_PORT ?= 6379

.PHONY: load
load: $(TARGET)
	@echo "Loading module into running Redis on port $(REDIS_PORT)..."
	$(REDIS_CLI) -p $(REDIS_PORT) MODULE LOAD $(PWD)/$(TARGET)

.PHONY: demo
demo: $(TARGET)
	pip install -q -r demo/requirements.txt
	@echo "Ensuring module is loaded in Redis on port $(REDIS_PORT)..."
	if echo "$$OUT" | grep -E -q 'OK|already loaded'; then \
		echo "Module loaded successfully."; \
	else \
		echo "Failed to load module. Error: $$OUT"; \
		echo "Hint: Redis 7+ disables MODULE LOAD at runtime by default."; \
		echo "      Restart your server with: redis-server --enable-module-command local"; \
		exit 1; \
	fi
	@sleep 1
	python3 demo/demo.py

.PHONY: clean
clean:
	rm -f $(OBJS) $(TARGET)
	cd $(GEMBED_DIR) && cargo clean
