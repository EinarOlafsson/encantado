#!/usr/bin/env bash
# Launch Encantado with the interpreter that has PyQt6, numpy and scipy.
cd "$(dirname "$0")"
exec /home/carruthers/anaconda3/envs/spacr/bin/python -m encantado "$@"
