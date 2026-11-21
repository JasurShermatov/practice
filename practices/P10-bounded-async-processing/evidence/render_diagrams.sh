#!/usr/bin/env bash
# Render every Mermaid source of the P10 practice to SVG and keep the log (render check).
#   bash practices/P10-bounded-async-processing/evidence/render_diagrams.sh
set -u
cd "$(dirname "$0")/../diagrams"
log=../evidence/logs/mmdc.txt
echo "# Mermaid CLI $(mmdc --version) with the container's headless Chromium (puppeteer-config.linux-build.json: --no-sandbox)" > "$log"
for source in *.mmd; do
  echo "\$ mmdc -p puppeteer-config.linux-build.json -i $source -o ${source%.mmd}.svg" >> "$log"
  mmdc -p puppeteer-config.linux-build.json -i "$source" -o "${source%.mmd}.svg" >> "$log" 2>&1
  echo "exit $?" >> "$log"
done
cat "$log"
