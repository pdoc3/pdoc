<form>
    <input id="lunr-search" name="q" placeholder="🔎 Search ..." aria-label="Search"
           disabled minlength="2">
</form>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/tingle/0.16.0/tingle.min.css" integrity="sha512-b+T2i3P45i1LZM7I00Ci5QquB9szqaxu+uuk5TUSGjZQ4w4n+qujQiIuvTv2BxE7WCGQCifNMksyKILDiHzsOg==" crossorigin>
<script src="https://cdnjs.cloudflare.com/ajax/libs/tingle/0.16.0/tingle.min.js" integrity="sha512-2B9/byNV1KKRm5nQ2RLViPFD6U4dUjDGwuW1GU+ImJh8YinPU9Zlq1GzdTMO+G2ROrB5o1qasJBy1ttYz0wCug==" crossorigin></script>
<style>
    .modal-dialog iframe {
        width: 100vw;
        height: calc(100vh - 80px);
    }
    @media screen and (min-width: 700px) {
        .modal-dialog iframe {
            width: 70vw;
            height: 80vh;
        }
    }
    .modal-dialog .tingle-modal-box {width: auto;}
    .modal-dialog .tingle-modal-box__content {padding: 0;}
</style>
<script>
    const input = document.getElementById('lunr-search');
    input.disabled = false;

    input.form.addEventListener('submit', (ev) => {
        ev.preventDefault();
        const url = new URL(window.location);
        url.searchParams.set('q', input.value);
        history.replaceState({}, null, url.toString());
        search(input.value);
    });

    ## On page load
    const query = new URL(window.location).searchParams.get('q');
    if (query)
        search(query);

    function search(query) {
        const url = '${'../' * module.url().count('/')}doc-search.html#' + encodeURIComponent(query);
        new tingle.modal({
            cssClass: ['modal-dialog'],
            onClose: () => {
                const url = new URL(window.location);
                url.searchParams.delete('q');
                history.replaceState({}, null, url.toString());
                setTimeout(() => input.focus(), 100);
            }
        }).setContent('<iframe src="' + url + '"></iframe>').open();
    }
</script>
