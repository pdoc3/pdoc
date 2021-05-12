<%def name="load_theme()">
  <%namespace name="theme" file="./themes/${context['css_theme']}.mako" />
  ${theme.style()}
  
  ######################################
  ## CSS Defs for components go here. ##
  ######################################
  
  html {
      background-color: var(--bg-default);
      cursor: auto;
  }

  #dark-mode-toggle {
    display: none;
    border: 1px solid;
    border-color: var(--bd-primary);
    color: var(--bd-primary);
    border-radius: 20px;
    padding-left: 6px;
    padding-right: 6px;
    cursor: pointer;
  }

  .hidden {
    visibility: hidden;
  }

  .dm-icon-off, .dm-icon-on {
    display: inline;
    width: 14px;
    height: 14px;
    margin-bottom: 4px;
  }

  h1:target,
  h2:target,
  h3:target,
  h4:target,
  h5:target,
  h6:target {
    background: var(--bg-highlight-color);
    padding: .2em 0;
  }

  .flex {
    display: flex;
  }

  body {
    line-height: 1.5em;
    color: var(--fc-default);
  }

  hr {
    border-color: var(--hr-default);
  }

  #sidebar {
    padding: 30px;
    overflow: hidden;
  }

  #sidebar > *:last-child {
    margin-bottom: 2cm;
  }

  % if lunr_search is not None:
  #lunr-search {
    width: 100%;
    font-size: 1em;
    padding: 6px 9px 5px 9px;
    border: 1px solid;
    border-color: var(--bd-primary);
    color: var(--fc-default);
    background: transparent;
    outline:none;
    border-radius: 10px;
    margin-top: 10px;
  }
  % endif

  .http-server-breadcrumbs {
    font-size: 130%;
    margin: 0 0 15px 0;
  }

  h1, h2, h3, h4, h5, h6 {
    font-weight: 300;
    color: var(--fc-default);
  }

  h1 {
    font-size: 2.5em;
    line-height: 1.1em;
  }

  h2 {
    font-size: 1.75em;
    margin: 1em 0 .50em 0;
  }

  h3 {
    font-size: 1.4em;
    margin: 25px 0 10px 0;
  }

  h4 {
    margin: 0;
    font-size: 105%;
  }

  #footer {
    font-size: .75em;
    padding: 5px 30px;
    border-top: 1px solid;
    border-color: var(--bd-default);
    text-align: right;
  }

  #footer p {
    margin: 0 0 0 1em;
    display: inline-block;
  }

  #footer p:last-child {
    margin-right: 30px;
  }

  a {
    color: var(--link-primary);
    text-decoration: none;
    transition: color .3s ease-in-out;
  }

  a:hover {
    color: var(--link-hover);
  }

  .title code {
    font-weight: bold;
  }

  h2[id^="header-"] {
    margin-top: 2em;
  }

  .ident {
    color: var(--ident-primary);
  }

  pre code {
    background: var(--bg-code);
    font-size: .8em;
    line-height: 1.4em;
  }

  code {
    background: var(--bg-code);
    padding: 1px 4px;
    overflow-wrap: break-word;
  }

  h1 code { background: transparent }

  pre {
    border-top: 1px solid;
    border-bottom: 1px solid;
    border-color: var(--bd-pre);
  }

  #http-server-module-list {
    display: flex;
    flex-flow: column;
  }

  #http-server-module-list div {
    display: flex;
  }

  #http-server-module-list dt {
    min-width: 10%;
  }

  #http-server-module-list p {
    margin-top: 0;
  }

  .toc ul, #index {
    list-style-type: none;
    margin: 0;
    padding: 0;
  }

  #index code {
    background: transparent;
  }

  #index h3 {
    border-bottom: 1px solid;
    border-color: var(--bd-default);
  }

  #index ul {
    padding: 0;
  }

  #index h4 {
    margin-top: .6em;
    font-weight: bold;
  }
  
  /* 
    Make TOC lists have 2+ columns when viewport is wide enough.
    Assuming ~20-character identifiers and ~30% wide sidebar.
  */

  @media (min-width: 200ex) { #index .two-column { column-count: 2 } }
  @media (min-width: 300ex) { #index .two-column { column-count: 3 } }

  dl {
    margin-bottom: 2em;
  }
  
  dl dl:last-child {
    margin-bottom: 4em;
  }
  
  dd {
    margin: 0 0 1em 3em;
  }
    
  #header-classes + dl > dd {
    margin-bottom: 3em;
  }
  
  dd dd {
    margin-left: 2em;
  }
  
  dd p {
    margin: 10px 0;
  }
    
  .name {
    background: var(--bg-code);
    font-weight: bold;
    font-size: .85em;
    padding: 5px 10px;
    display: inline-block;
    min-width: 40%;
  }
      
  .name:hover {
    background: var(--bg-code-hover);
  }
  
  dt:target .name {
    background: var(--highlight-color);
  }
  
  .name > span:first-child {
    white-space: nowrap;
  }
  
  .name.class > span:nth-child(2) {
    margin-left: .4em;
  }

  .inherited {
    color: #999; /* NOTE: Not entirely sure how to check this one.. Seems ok already?? */
    border-left: 5px solid #eee;
    padding-left: 1em;
  }

  .inheritance em {
    font-style: normal;
    font-weight: bold;
  }

  /* Docstrings titles, e.g. in numpydoc format */
  
  .desc h2 {
    font-weight: 400;
    font-size: 1.25em;
  }
  
  .desc h3 {
    font-size: 1em;
  }
    
  .desc dt code {
    background: inherit;  /* Don't grey-back parameters */
  }

  .source summary, .git-link-div {
    outline: none;
    color: var(--fc-muted);
    text-align: right;
    font-weight: 400;
    font-size: .8em;
    text-transform: uppercase;
  }

  .source summary > * {
    white-space: nowrap;
    cursor: pointer;
  }

  .git-link {
    color: inherit;
    margin-left: 1em;
  }

  .source pre {
    max-height: 500px;
    overflow: auto;
    margin: 0;
  }

  .source pre code {
    font-size: 12px;
    overflow: visible;
  }

  .hlist {
    list-style: none;
  }

  .hlist li {
    display: inline;
  }

  .hlist li:after {
    content: ',\2002';
  }

  .hlist li:last-child:after {
    content: none;
  }

  .hlist .hlist {
    display: inline;
    padding-left: 1em;
  }

  img {
    max-width: 100%;
  }

  td {
    padding: 0 .5em;
  }

  .admonition {
    padding: .1em .5em;
    margin-bottom: 1em;
    border-radius: 8px;
    border: 1px solid;
  }

  .admonition-title {
    font-weight: bold;
  }

  .admonition.note,
  .admonition.info,
  .admonition.important {
    background: var(--adm-note);
    border-color: var(--adm-bd-note);
  }

  .admonition.todo,
  .admonition.versionadded,
  .admonition.tip,
  .admonition.hint {
    background: var(--adm-todo);
    border-color: var(--adm-bd-todo);
  }
  
  .admonition.warning,
  .admonition.versionchanged,
  .admonition.deprecated {
    background: var(--adm-warning);
    border-color: var(--adm-bd-warning);
  }

  .admonition.error,
  .admonition.danger,
  .admonition.caution {
    background: var(--adm-error);
    border-color: var(--adm-bd-error);
  }

  /* 
    Desktop MQuery

    * Standard desktop breakpoint is 1024, below are tablets and portables.
    * No need to limit the max-width of #content, otherwise space is being wasted.
  */

  @media screen and (min-width: 1024px) { 
    #dark-mode-toggle {
      display: block;
      position: absolute;
      top: 5px;
      right: 5px;
    }
    #sidebar {
      width: 30%;
      height: 100vh;
      overflow: auto;
      position: sticky;
      top: 0;
    }

    #content {
      width: 100%;
      padding: 3em 4em;
      border-left: 1px solid var(--bd-default);
    }

    pre code {
      font-size: 1em;
    }

    .item .name {
      font-size: 1em;
    }

    main {
      display: flex;
      flex-direction: row-reverse;
      justify-content: flex-end;
    }

    .toc ul ul, #index ul {
      padding-left: 1.5em;
    }

    .toc > ul > li {
      margin-top: .5em;
    }
  }


@media print {
    * {
        background: transparent !important;
        color: #000 !important; /* Black prints faster: h5bp.com/s */
        box-shadow: none !important;
        text-shadow: none !important;
    }

    #sidebar h1 {
      page-break-before: always;
    }

    .source {
      display: none;
    }

    a[href]:after {
        content: " (" attr(href) ")";
        font-size: 90%;
    }

    /* Internal, documentation links, recognized by having a title, don't need the URL explicity stated. */
    
    a[href][title]:after {
        content: none;
    }

    abbr[title]:after {
        content: " (" attr(title) ")";
    }

    /* Don't show links for images, or javascript/internal links */

    .ir a:after,
    a[href^="javascript:"]:after,
    a[href^="#"]:after {
        content: "";
    }

    pre, blockquote {
        border: 1px solid #999;
        page-break-inside: avoid;
    }

    thead {
        display: table-header-group; /* h5bp.com/t */
    }

    tr, img {
        page-break-inside: avoid;
    }

    img {
        max-width: 100% !important;
    }

    @page {
        margin: 0.5cm;
    }

    p, h2, h3 {
      orphans: 3;
      widows: 3;
    }

    h1, h2, h3, h4, h5, h6 {
      page-break-after: avoid;
    }
}
</%def>
