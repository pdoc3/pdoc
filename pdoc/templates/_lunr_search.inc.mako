<form>
    <input id="lunr-search" name="q" placeholder="🔎 Search ..." aria-label="Search"
           disabled minlength="2">
</form>
<link rel="preload stylesheet" as="style" href="https://cdnjs.cloudflare.com/ajax/libs/tingle/0.15.3/tingle.min.css" integrity="sha512-j1u8eUJ4f23xPPxwOrLUPQaCD2dwzNqqmDDcWS4deWsMv2ohLqmXXuP3hU7g8TyzbMSakP/mMqoNBYWj8AEIFg==" crossorigin>
<script src="https://cdnjs.cloudflare.com/ajax/libs/tingle/0.15.3/tingle.min.js" integrity="sha512-plGUER9JkeEWPPqQBE4sdLqBoQug5Ap+BCGMc7bJ8BXkm+VVj6QzkpBz5Yv2yPkkq+cqg9IpkBaGCas6uDbW8g==" crossorigin></script>
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
