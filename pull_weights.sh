#!/bin/bash
set -e

SAM3_DIR="/opt/checkpoints/sam3"
SAM3_WEIGHT_FILE="$SAM3_DIR/sam3.pt"
SAM3_CONFIG_FILE="$SAM3_DIR/config.json"
CLIP_BPE_FILE="$SAM3_DIR/bpe_simple_vocab_16e6.txt.gz"

mkdir -p "$SAM3_DIR"

# Download SAM3 weights + config if missing
if [ ! -f "$SAM3_WEIGHT_FILE" ] || [ ! -f "$SAM3_CONFIG_FILE" ]; then
    hf download --token "$HF_TOKEN" facebook/sam3 \
        sam3.pt config.json \
        --local-dir "$SAM3_DIR"
fi

# Download CLIP BPE vocab if missing
if [ ! -f "$CLIP_BPE_FILE" ]; then
    curl -L \
        https://raw.githubusercontent.com/openai/CLIP/main/clip/bpe_simple_vocab_16e6.txt.gz \
        -o "$CLIP_BPE_FILE"
fi