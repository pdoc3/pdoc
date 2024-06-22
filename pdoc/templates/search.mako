<!doctype html>
<html lang="${html_lang}">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, minimum-scale=1">
    <title>Search</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/10up-sanitize.css/13.0.0/sanitize.min.css" integrity="sha512-y1dtMcuvtTMJc1yPgEqF0ZjQbhnc/bFhyvIyVNb9Zk5mIGtqVaAB1Ttl28su8AvFMOY0EwRbAe+HCLqj6W7/KA==" crossorigin>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/10up-sanitize.css/13.0.0/typography.min.css" integrity="sha512-Y1DYSb995BAfxobCkKepB1BqJJTPrOp3zPL74AWFugHHmmdcvO+C48WLrUOlhGMc0QG7AE3f7gmvvcrmX2fDoA==" crossorigin>
    <style>
        body {margin: 0 1em;}
        footer,
        #search-status {
            font: 14px normal;
            color: grey;
        }

        footer {text-align: right;}

        a {
            color: #058;
            text-decoration: none;
            transition: color .3s ease-in-out;
        }
        a:hover {color: #e82;}

        li {padding-top: 10px;}
    </style>
    <base target="_parent">
</head>
<body>
<noscript>
    JavaScript is not supported/enabled in your browser. The search feature won't work.
</noscript>
<main>
    <h3 id="search-status"></h3>
    <ul id="search-results"></ul>
</main>
<footer>
    <p>Search results provided by <a href="https://lunrjs.com">Lunr.js</a></p>
</footer>

<script src="index.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/lunr.js/2.3.9/lunr.min.js" integrity="sha512-4xUl/d6D6THrAnXAwGajXkoWaeMNwEKK4iNfq5DotEbLPAfk6FSxSP3ydNxqDgCw1c/0Z1Jg6L8h2j+++9BZmg==" crossorigin></script>
<script>
    'use strict';

    const lunr_index = build_index();
    search(decodeURIComponent(new URL(window.location).hash.substring(1)));

    function set_status(message) {
        document.getElementById('search-status').textContent = message;
    }

    async function build_index() {
        try {
            return lunr.Index.load(_expand(INDEX));  // Prebuilt index
        } catch {
            return lunr(function () {
            this.ref('i');
            this.field('name', {boost: 10});
            this.field('ref', {boost: 5});
            this.field('doc');
            this.metadataWhitelist = ['position'];

            INDEX.forEach((doc, i) => {
                const parts = doc.ref.split('.');
                doc['name'] = parts[parts.length - 1];
                doc['i'] = i;

                this.add(doc);
            }, this);
        });
        }
    }

    function _expand(compact) {
        // https://john-millikin.com/compacting-lunr-search-indices
        const fields = compact["fields"];
        const fieldVectors = compact["fieldVectors"].map((item) => {
            const id = item[0];
            const vectors = item[1];
            let prev = null;
            const expanded = vectors.map((v, ii) => {
                if (ii % 2 === 0) {
                    if (v === null) {
                        v = prev + 1;
                    }
                    prev = v;
                }
                return v;
            });
            return [id, expanded];
        });
        const invertedIndex = compact["invertedIndex"].map((item, itemIdx) => {
            const token = item[0];
            const fieldMap = {"_index": itemIdx};
            fields.forEach((field, fieldIdx) => {
                const matches = {};
                let docRef = null;
                item[fieldIdx + 1].forEach((v, ii) => {
                    if (ii % 2 === 0) {
                        docRef = fieldVectors[v][0].slice((field + '/').length);
                    } else {
                        matches[docRef] = v;
                    }
                });
                fieldMap[field] = matches;
            })
            return [token, fieldMap];
        });
        invertedIndex.sort((a, b) => {
            if (a[0] < b[0]) {
                return -1;
            }
            if (a[0] > b[0]) {
                return 1;
            }
            return 0;
        });
        return {
            "version": compact["version"],
            "fields": fields,
            "fieldVectors": fieldVectors,
            "invertedIndex": invertedIndex,
            "pipeline": compact["pipeline"],
        };
    }

    function search(query) {
        _search(query).catch(err => {
            set_status("Something went wrong. See development console for details.");
            throw err;
        });
    }

    async function _search(query) {
        if (!query) {
            set_status('No query provided, so there is nothing to search.');
            return;
        }

        const fuzziness = ${int(lunr_search.get('fuzziness', 1))};
        if (fuzziness) {
            query = query.split(/\s+/)
                    .map(str => str.includes('~') ? str : str + '~' + fuzziness).join(' ');
        }

        const results = (await lunr_index).search(query);
        if (!results.length) {
            set_status('No results match your query.');
            return;
        }

        set_status(
            'Search for "' + encodeURIComponent(query) + '" yielded ' + results.length + ' ' +
            (results.length === 1 ? 'result' : 'results') + ':');

        results.forEach(function (result) {
            const dobj = INDEX[parseInt(result.ref)];
            const docstring = dobj.doc;
            const url = URLS[dobj.url] + '#' + dobj.ref;
            const pretty_name = dobj.ref + (dobj.func ? '()' : '');
            let text = '';
            if (docstring) {
                text = Object.values(result.matchData.metadata)
                        .filter(({doc}) => doc !== undefined)
                        .map(({doc: {position}}) => {
                            return position.map(([start, length]) => {
                                const PAD_CHARS = 30;
                                const end = start + length;
                                ## TODO: merge overlapping matches
                                return [
                                    start,
                                    (start - PAD_CHARS > 0 ? '…' : '') +
                                    docstring.substring(start - PAD_CHARS, start) +
                                    '<mark>' + docstring.slice(start, end) + '</mark>' +
                                    docstring.substring(end, end + PAD_CHARS) +
                                    (end + PAD_CHARS < docstring.length ? '…' : '')
                                ];
                            });
                        })
                        .flat()
                        .sort(([pos1,], [pos2,]) => pos1 - pos2)
                        .map(([, text]) => text)
                        .join('')
                        .replace(/……/g, '…');
            }

            if (text)
                text = '<div>' + text + '</div>';
            text = '<a href="' + url + '"><code>' + pretty_name + '</code></a>' + text;

            const li = document.createElement('li');
            li.innerHTML = text;
            document.getElementById('search-results').appendChild(li);
        });
    }
</script>
</body>
