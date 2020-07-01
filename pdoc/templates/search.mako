<%def name="html()">
<article id='content'>
    <h1>Search the docs</h1>
    <h3 id="search-status"></h3>
    <div id="search-results"></div>
    <noscript>
    <h3>JavaScript is not supported/enabled in your browser, so the search function will not work</h3>
    </noscript>
</article>
</%def>

## Version of lunr.js is frozen to 2.3.8, update here if necesary
<%def name="js()">
<script src="index.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/lunr.js/2.3.8/lunr.js" integrity="sha256-JZUIb2pF9vF82f9JemSl6XISUBX4tvjrprJM21J63G8=" crossorigin></script>
<script>
var searchBox = document.getElementById('search-box');
var searchStatus = document.getElementById('search-status');
var searchResults = document.getElementById('search-results');
var q = new URLSearchParams(window.location.search).get('q');
    
if (q === null || q === '') {
    searchStatus.innerHTML = 'Use the search box to search the documentation.';
} else {
    searchBox.value = q;

    try {
        var documentsIndex = {};
        var idx = lunr(function () {
                this.ref('ref');
                this.field('refname', {'boost':10});
                this.field('name', {'boost': 5});
                this.field('docstring');
                this.metadataWhitelist = ['position'];

                index.forEach(function(doc) { 
                    this.add(doc);
                    documentsIndex[doc.ref] = {
                        'refname': doc.refname,
                        'name': doc.name,
                        'docstring': doc.docstring,
                    };
                }, this);
            });

        var fuzziness = ${lunr_search_fuzziness};
        if (fuzziness != 0) {
            q += "~" + fuzziness;
        };
        
        var results = idx.search(q);

        if (results.length == 0) {
            searchStatus.innerHTML = 'No results have been found for your search. Make sure that all words are spelled correctly.';
        } else {
            var ul = document.createElement('ul');
            var count = 0;
            results.forEach(function(result) {
                var liLink = '<a href="' + result.ref + '">' + documentsIndex[result.ref].refname + '</a>';

                Object.keys(result.matchData.metadata).forEach(function (term) {
                    if (!('name' in result.matchData.metadata[term] || 'refname' in result.matchData.metadata[term])) {
                        var docstring = documentsIndex[result.ref].docstring;

                        result.matchData.metadata[term].docstring.position.forEach(function(positions) {
                            var start;
                            if (positions[0] - 180 > 0) {
                                start = '...' + docstring.slice(positions[0] - 180, positions[0]);
                            } else {
                                start = docstring.slice(0, positions[0]);
                            };

                            var match = docstring.slice(positions[0], positions[0] + positions[1]);

                            var end;
                            if (positions[0] + positions[1] + 180 < docstring.length) {
                                end = docstring.slice(positions[0] + positions[1], positions[0] + positions[1] + 180) + '...';
                            } else {
                                end = docstring.slice(positions[0] + positions[1], docstring.length);
                            };

                            var liContent = '<div class="content">' + start + '<mark>' + match + '</mark>' + end + '</div>';

                            var li = document.createElement('li');
                            li.innerHTML = liLink + liContent;
                            ul.appendChild(li);
                            count += 1
                        });
                    } else {
                        var li = document.createElement('li');
                        li.innerHTML = liLink;
                        ul.appendChild(li);
                        count += 1
                    };
                });
            });

            searchResults.appendChild(ul);

            searchStatus.innerHTML = 'Your search brought back ' + count + ' result(s):';
        };
    } catch {
        searchStatus.innerHTML = `Something went wrong and the results couldn't get displayed`;
    };
};
</script>
</%def>