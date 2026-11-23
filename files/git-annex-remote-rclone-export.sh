#!/usr/bin/bash

# SPDX-FileCopyrightText: Robert Ryszard Paciorek <rrp@opcode.eu.org>
# SPDX-License-Identifier: MIT

# created by Gemini AI, 2026

set -euo pipefail

echo "VERSION 1"

RCD_PID=""
RC_ADDR=""

cleanup() {
    if [ -n "$RCD_PID" ] && kill -0 "$RCD_PID" 2>/dev/null; then
        kill "$RCD_PID" 2>/dev/null || true
    fi
}
trap cleanup EXIT

is_ignored() {
    local filepath="$1"
    local filename="${filepath##*/}"
    for pattern in $IGNORE_PATTERNS; do
        if [[ "$filepath" == $pattern || "$filename" == $pattern ]]; then
            return 0
        fi
    done
    return 1
}

IGNORE_PATTERNS=""

while IFS= read -r line; do
    read -r cmd rest <<< "$line"
    case "$cmd" in
        EXTENSIONS)
            echo "EXTENSIONS"
            ;;
        EXPORTSUPPORTED)
            echo "EXPORTSUPPORTED-SUCCESS"
            ;;
        INITREMOTE)
            echo "INITREMOTE-SUCCESS"
            ;;
        PREPARE)
            echo "GETGITREMOTENAME"
            IFS= read -r resp
            REMOTE_NAME="${resp#VALUE }"

            if [ -z "$REMOTE_NAME" ]; then
                echo "PREPARE-FAILURE Nie udało się ustalić nazwy remote'a"
            else
                TARGET=$(git config --get "remote.${REMOTE_NAME}.rclone-target" || true)
                IGNORE_PATTERNS=$(git config --get-all "remote.${REMOTE_NAME}.export-ignore" | tr '\n' ' ' || true)

                if [ -z "$TARGET" ]; then
                    echo "PREPARE-FAILURE Brak ustawionego remote.${REMOTE_NAME}.rclone-target w git config"
                else
                    # Rozdzielenie TARGET (np. "mega:kopie/pliki") na FS ("mega:") i ścieżkę bazową ("kopie/pliki")
                    REMOTE_FS="${TARGET%%:*}:"
                    BASE_PATH="${TARGET#*:}"
                    BASE_PATH="${BASE_PATH#/}"
                    BASE_PATH="${BASE_PATH%/}"

                    # Start rclone rcd na losowym wolnym porcie
                    PORT=$(python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1",0)); print(s.getsockname()[1]); s.close()')
                    RC_ADDR="127.0.0.1:${PORT}"
                    rclone rcd --rc-addr="$RC_ADDR" --rc-no-auth --quiet &
                    RCD_PID=$!

                    # Czekaj na gotowość API (maks. 5s)
                    for _ in $(seq 1 50); do
                        if rclone rc --rc-addr="$RC_ADDR" core/version >/dev/null 2>&1; then
                            break
                        fi
                        sleep 0.1
                    done

                    echo "PREPARE-SUCCESS"
                fi
            fi
            ;;
        EXPORT)
            EXPORT_NAME="$rest"
            ;;
        TRANSFEREXPORT)
            read -r dir key file <<< "$rest"
            FULL_DST="${BASE_PATH:+${BASE_PATH}/}${EXPORT_NAME}"
            SRC_ABS=$(realpath "$file")
            SRC_DIR=$(dirname "$SRC_ABS")
            SRC_FILE=$(basename "$SRC_ABS")
            DST_DIR=$(dirname "$FULL_DST")
            DST_FILE=$(basename "$FULL_DST")
            [ "$DST_DIR" = "." ] && DST_DIR=""

            if is_ignored "$EXPORT_NAME"; then
                echo "TRANSFER-SUCCESS STORE $key"
            elif [ "$dir" = "STORE" ]; then
                if rclone rc --rc-addr="$RC_ADDR" operations/copyfile \
                    srcFs="$SRC_DIR" srcRemote="$SRC_FILE" \
                    dstFs="${REMOTE_FS}${DST_DIR}" dstRemote="$DST_FILE" >/dev/null 2>&1; then
                    echo "TRANSFER-SUCCESS STORE $key"
                else
                    echo "TRANSFER-FAILURE STORE $key Błąd wysyłania rclone"
                fi
            else
                echo "TRANSFER-FAILURE $dir $key Pobieranie nie jest obsługiwane"
            fi
            ;;
        CHECKPRESENTEXPORT)
            key="$rest"
            FULL_DST="${BASE_PATH:+${BASE_PATH}/}${EXPORT_NAME}"
            DST_DIR=$(dirname "$FULL_DST")
            [ "$DST_DIR" = "." ] && DST_DIR=""

            if is_ignored "$EXPORT_NAME"; then
                echo "CHECKPRESENT-SUCCESS $key"
            elif rclone rc --rc-addr="$RC_ADDR" operations/stat \
                fs="${REMOTE_FS}${DST_DIR}" remote="$(basename "$FULL_DST")" 2>/dev/null | grep -q '"Size"'; then
                echo "CHECKPRESENT-SUCCESS $key"
            else
                echo "CHECKPRESENT-FAILURE $key"
            fi
            ;;
        REMOVEEXPORT)
            key="$rest"
            FULL_DST="${BASE_PATH:+${BASE_PATH}/}${EXPORT_NAME}"
            if ! is_ignored "$EXPORT_NAME"; then
                rclone rc --rc-addr="$RC_ADDR" operations/deletefile \
                    fs="$REMOTE_FS" remote="$FULL_DST" >/dev/null 2>&1 || true
            fi
            echo "REMOVE-SUCCESS $key"
            ;;
        REMOVEEXPORTDIRECTORY)
            FULL_DIR="${BASE_PATH:+${BASE_PATH}/}${rest}"
            rclone rc --rc-addr="$RC_ADDR" operations/rmdir \
                fs="$REMOTE_FS" remote="$FULL_DIR" >/dev/null 2>&1 || true
            echo "REMOVEEXPORTDIRECTORY-SUCCESS"
            ;;
        RENAMEEXPORT)
            key="${rest%% *}"
            new_name="${rest#* }"
            FULL_SRC="${BASE_PATH:+${BASE_PATH}/}${EXPORT_NAME}"
            FULL_DST="${BASE_PATH:+${BASE_PATH}/}${new_name}"
            if is_ignored "$EXPORT_NAME" && is_ignored "$new_name"; then
                echo "RENAMEEXPORT-SUCCESS $key"
            elif rclone rc --rc-addr="$RC_ADDR" operations/movefile \
                srcFs="$REMOTE_FS" srcRemote="$FULL_SRC" \
                dstFs="$REMOTE_FS" dstRemote="$FULL_DST" >/dev/null 2>&1; then
                echo "RENAMEEXPORT-SUCCESS $key"
            else
                echo "RENAMEEXPORT-FAILURE $key"
            fi
            ;;
        *)
            echo "UNSUPPORTED-REQUEST"
            ;;
    esac
done
