#!/bin/bash
# Stacks one strip per take into a single image: one frame per second, each stamped with its time in the take.
#   take_strips.sh OUT.png SECONDS TAKE.avi[@START] ...
# START is the first gameplay frame, in seconds (after menu and loading); each strip covers SECONDS from it.
# With replay_rec.gd sessions: awk -F, '$2!="-"{print $1/60; exit}' session/state.csv
set -euo pipefail
[ $# -ge 3 ] || { sed -n '2,5p' "$0"; exit 1; }
OUT=$1; SECONDS_SHOWN=$2; shift 2
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
INPUTS=(); i=0
for ARG in "$@"; do
  TAKE=${ARG%@*}; START=0
  [ "$ARG" != "$TAKE" ] && START=${ARG##*@}
  NAME=$(basename "$TAKE"); NAME=${NAME%.*}
  ffmpeg -v error -y -ss "$START" -t "$SECONDS_SHOWN" -i "$TAKE" -vf "fps=1,scale=192:-2,\
drawtext=text='%{pts\:hms\:$START}':x=3:y=3:fontsize=15:fontcolor=white:box=1:boxcolor=black,\
tile=${SECONDS_SHOWN}x1:color=black,pad=iw:ih+26:0:26,\
drawtext=text='$NAME  from ${START}s':x=4:y=4:fontsize=18:fontcolor=white" -frames:v 1 "$TMP/$i.png"
  INPUTS+=(-i "$TMP/$i.png"); i=$((i + 1))
done
if [ "$i" -eq 1 ]; then cp "$TMP/0.png" "$OUT"
else ffmpeg -v error -y "${INPUTS[@]}" -filter_complex "vstack=inputs=$i" "$OUT"; fi
echo "$OUT: $i takes, ${SECONDS_SHOWN} s each"
