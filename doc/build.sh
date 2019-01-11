#!/bin/bash
set -eu
IS_RELEASE=${TRAVIS_TAG+1}

die () { echo "ERROR: $*" >&2; exit 2; }

for cmd in pdoc3; do
    command -v "$cmd" >/dev/null ||
        die "Missing $cmd; \`pip install $cmd\`"
done

DOCROOT="$(dirname "$(readlink -f "$0")")"
BUILDROOT="$DOCROOT/build"


echo
echo 'Building API reference docs'
echo
mkdir -p "$BUILDROOT"
rm -r "$BUILDROOT" 2>/dev/null || true
pushd "$DOCROOT/.." >/dev/null
pdoc3 --html \
     ${IS_RELEASE+--template-dir "$DOCROOT/pdoc_template"} \
     --html-dir "$BUILDROOT" \
     pdoc
popd >/dev/null


if [ "$IS_RELEASE" ]; then
    echo -e '\nAdding GAnalytics code\n'

    ANALYTICS="<script>window.ga=window.ga||function(){(ga.q=ga.q||[]).push(arguments)};ga.l=+new Date;ga('create','UA-43663477-5','auto');ga('require','cleanUrlTracker',{indexFilename:'index.html',trailingSlash:'add'});ga('require','outboundLinkTracker',{events:['click','auxclick','contextmenu']});ga('require','maxScrollTracker');ga('require','pageVisibilityTracker');ga('send','pageview');setTimeout(function(){ga('send','event','pageview','view')},15000);</script><script async src='https://www.google-analytics.com/analytics.js'></script><script async src='https://cdnjs.cloudflare.com/ajax/libs/autotrack/2.4.1/autotrack.js'></script>"
    find "$BUILDROOT" -name '*.html' -print0 |
        xargs -0 -- sed -i "s#</body>#$ANALYTICS</body>#i"
fi


echo
echo 'Testing for broken links'
echo
pushd "$BUILDROOT" >/dev/null
grep -PR '<a .*?href=' |
    sed -E "s/:.*?<a .*?href=([\"'])(.*?)/\t\2/g" |
    tr "\"'" '#' |
    cut -d'#' -f1 |
    sort -u -t$'\t' -k 2 |
    sort -u |
    python -c '
import sys
from urllib.parse import urljoin
for line in sys.stdin.readlines():
    base, url = line.split("\t")
    print(base, urljoin(base, url.strip()), sep="\t")
    ' |
    grep -v $'\t''$' |
    while read -r line; do
        while IFS=$'\t' read -r file url; do
            [ -f "$url" ] ||
                curl --silent --fail --retry 2 --user-agent 'Mozilla/5.0 Firefox 61' "$url" >/dev/null 2>&1 ||
                die "broken link in $file:  $url"
        done
    done
popd >/dev/null


echo
echo "All good. Docs in: $BUILDROOT"
echo
echo "    file://$BUILDROOT/pdoc/index.html"
echo
