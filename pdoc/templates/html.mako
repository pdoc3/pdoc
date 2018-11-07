<%!
    # Template configuration
    html_lang = 'en'
    show_inherited_members = True
%>
<%
  import os
  import re
  import sys

  import markdown

  import pdoc

  # From language reference, but adds '.' to allow fully qualified names.
  pyident = re.compile('^[a-zA-Z_][a-zA-Z0-9_.]+$')

  # Whether we're showing the module list or a single module.
  module_list = 'modules' in context.keys()

  def linkify(match):
    matched = match.group(0)
    ident = matched[1:-1]
    name, url = lookup(ident)
    if name is None:
      return matched
    return '[`%s`](%s)' % (name, url)

  def mark(s, linky=True):
    if linky:
      s, _ = re.subn('\b\n\b', ' ', s)
    if not module_list:
      s, _ = re.subn('`[^`]+`', linkify, s)

    extensions = []
    s = markdown.markdown(s.strip(), extensions=extensions)
    return s

  def glimpse(s, length=100):
    if len(s) < length:
      return s
    return s[0:length] + '...'

  def module_url(m):
    """
    Returns a URL for `m`, which must be an instance of `Module`.
    Also, `m` must be a submodule of the module being documented.

    Namely, '.' import separators are replaced with '/' URL
    separators. Also, packages are translated as directories
    containing `index.html` corresponding to the `__init__` module,
    while modules are translated as regular HTML files with an
    `.m.html` suffix. (Given default values of
    `pdoc.html_module_suffix` and `pdoc.html_package_name`.)
    """
    if module.name == m.name:
      return ''

    base = m.name.replace('.', '/')
    if len(link_prefix) == 0:
      base = os.path.relpath(base, module.name.replace('.', '/'))
    url = (base[len('../'):] if base.startswith('../') else
           '' if base == '..' else
           base)
    if m.is_package:
      index = pdoc.html_package_name
      url = url + '/' + index if url else index
    else:
      url += pdoc.html_module_suffix
    return link_prefix + url

  def external_url(refname):
    """
    Attempts to guess an absolute URL for the external identifier
    given.

    Note that this just returns the refname with an ".ext" suffix.
    It will be up to whatever is interpreting the URLs to map it
    to an appropriate documentation page.
    """
    return '/%s.ext' % refname

  def is_external_linkable(name):
    return external_links and pyident.match(name) and '.' in name

  def lookup(refname):
    """
    Given a fully qualified identifier name, return its refname
    with respect to the current module and a value for a `href`
    attribute. If `refname` is not in the public interface of
    this module or its submodules, then `None` is returned for
    both return values. (Unless this module has enabled external
    linking.)

    In particular, this takes into account sub-modules and external
    identifiers. If `refname` is in the public API of the current
    module, then a local anchor link is given. If `refname` is in the
    public API of a sub-module, then a link to a different page with
    the appropriate anchor is given. Otherwise, `refname` is
    considered external and no link is used.
    """
    d = module.find_ident(refname)
    if isinstance(d, pdoc.External):
      if is_external_linkable(refname):
        return d.refname, external_url(d.refname)
      else:
        return None, None
    if isinstance(d, pdoc.Module):
      return d.refname, module_url(d)
    if module.is_public(d.refname):
      return d.name, '#%s' % d.refname
    return d.refname, '%s#%s' % (module_url(d.module), d.refname)

  def link(refname):
    """
    A convenience wrapper around `href` to produce the full
    `a` tag if `refname` is found. Otherwise, plain text of
    `refname` is returned.
    """
    name, url = lookup(refname)
    if name is None:
      return refname
    return '<a href="%s">%s</a>' % (url, name)
%>
<%def name="ident(name)"><span class="ident">${name}</span></%def>

<%def name="show_source(d)">
    % if show_source_code and d.source and d.obj is not getattr(d.inherits, 'obj', None):
        <details class="source">
            <summary>Source code</summary>
            <pre><code class="python">${d.source | h}}</code></pre>
        </details>
    %endif
</%def>

<%def name="show_desc(d, limit=None)">
  <%
  inherits = (' class="inherited"'
              if d.inherits and (not d.docstring or d.docstring == d.inherits.docstring) else
              '')
  docstring = d.inherits.docstring if inherits else d.docstring
  if limit is not None:
    docstring = glimpse(docstring, limit)
  %>
  % if d.inherits:
      <p class="inheritance">
          <em>Inherited from:</em>
          % if hasattr(d.inherits, 'cls'):
              <code>${link(d.inherits.cls.refname)}</code>.<code>${link(d.inherits.refname)}</code>
          % else:
              <code>${link(d.inherits.refname)}</code>
          % endif
      </p>
  % endif
  <div${inherits}>${docstring | mark}</div>
  % if not isinstance(d, pdoc.Module):
  ${show_source(d)}
  % endif
</%def>

<%def name="show_module_list(modules)">
<h1>Python module list</h1>

% if not modules:
  <p>No modules found.</p>
% else:
  <dl id="http-server-module-list">
  % for name, desc in modules:
      <div class="flex">
      <dt><a href="${link_prefix}${name}">${name}</a></dt>
      <dd>${desc | glimpse, mark}</dd>
      </div>
  % endfor
  </dl>
% endif
</%def>

<%def name="show_column_list(items)">
  <ul class="${'two-column' if len(items) >= 6 else ''}">
  % for item in items:
    <li><code>${link(item.refname)}</code></li>
  % endfor
  </ul>
</%def>

<%def name="show_module(module)">
  <%
  variables = module.variables()
  classes = module.classes()
  functions = module.functions()
  submodules = module.submodules()
  %>

  <%def name="show_func(f)">
    <dt id="${f.refname}"><code class="name flex">
        <span>${f.funcdef()} ${ident(f.name)}</span>(<span>${', '.join(f.params()) | h})</span>
    </code></dt>
    <dd>${show_desc(f)}</dd>
  </%def>

  <header>
  % if 'http_server' in context.keys():
    <nav class="http-server-breadcrumbs">
      <a href="/">All packages</a>
      <% parts = module.name.split('.')[:-1] %>
      % for i, m in enumerate(parts):
        <% parent = '.'.join(parts[:i+1]) %>
        :: <a href="/${parent.replace('.', '/')}">${parent}</a>
      % endfor
    </nav>
  % endif
  <h1 class="title"><code>${module.name}</code> module</h1>
  </header>

  <section id="section-intro">
  ${module.docstring | mark}
  ${show_source(module)}
  </section>

  <section>
    % if submodules:
    <h2 class="section-title" id="header-submodules">Sub-modules</h2>
    <dl>
    % for m in submodules:
      <dt><code class="name">${link(m.refname)}</code></dt>
      <dd>${show_desc(m, limit=300)}</dd>
    % endfor
    </dl>
    % endif
  </section>

  <section>
    % if variables:
    <h2 class="section-title" id="header-variables">Global variables</h2>
    <dl>
    % for v in variables:
      <dt id="${v.refname}"><code class="name">var ${ident(v.name)}</code></dt>
      <dd>${show_desc(v)}</dd>
    % endfor
    </dl>
    % endif
  </section>

  <section>
    % if functions:
    <h2 class="section-title" id="header-functions">Functions</h2>
    <dl>
    % for f in functions:
      ${show_func(f)}
    % endfor
    </dl>
    % endif
  </section>

  <section>
    % if classes:
    <h2 class="section-title" id="header-classes">Classes</h2>
    <dl>
    % for c in classes:
      <%
      class_vars = c.class_variables(show_inherited_members)
      smethods = c.functions(show_inherited_members)
      inst_vars = c.instance_variables(show_inherited_members)
      methods = c.methods(show_inherited_members)
      mro = c.mro()
      subclasses = c.subclasses()
      %>
      <dt id="${c.refname}"><code class="flex name class">
          <span>class ${ident(c.name)}</span>
          % if mro:
              <span>(</span><span><small>ancestors:</small> ${', '.join(link(cls.refname) for cls in mro)})</span>
          %endif
      </code></dt>

      <dd>${show_desc(c)}

      % if subclasses:
          <h3>Subclasses</h3>
          <ul class="hlist">
          % for sub in subclasses:
              <li>${link(sub.refname)}</li>
          % endfor
          </ul>
      % endif
      % if class_vars:
          <h3>Class variables</h3>
          <dl>
          % for v in class_vars:
              <dt id="${v.refname}"><code class="name">var ${ident(v.name)}</code></dt>
              <dd>${show_desc(v)}</dd>
          % endfor
          </dl>
      % endif
      % if smethods:
          <h3>Static methods</h3>
          <dl>
          % for f in smethods:
              ${show_func(f)}
          % endfor
          </dl>
      % endif
      % if inst_vars:
          <h3>Instance variables</h3>
          <dl>
          % for v in inst_vars:
              <dt id="${v.refname}"><code class="name">var ${ident(v.name)}</code></dt>
              <dd>${show_desc(v)}</dd>
          % endfor
          </dl>
      % endif
      % if methods:
          <h3>Methods</h3>
          <dl>
          % for f in methods:
              ${show_func(f)}
          % endfor
          </dl>
      % endif
      </dd>
    % endfor
    </dl>
    % endif
  </section>
</%def>

<%def name="module_index(module)">
  <%
  variables = module.variables()
  classes = module.classes()
  functions = module.functions()
  submodules = module.submodules()
  supermodule = module.supermodule
  %>
  <nav id="sidebar">
    <h1>Index</h1>
    <ul id="index">
    % if supermodule:
    <li><h3>Super-module</h3>
      <ul>
        <li><code>${link(supermodule.refname)}</code></li>
      </ul>
    </li>
    % endif

    % if submodules:
    <li><h3><a href="#header-submodules">Sub-modules</a></h3>
      <ul>
      % for m in submodules:
        <li><code>${link(m.refname)}</code></li>
      % endfor
      </ul>
    </li>
    % endif

    % if variables:
    <li><h3><a href="#header-variables">Global variables</a></h3>
      ${show_column_list(variables)}
    </li>
    % endif

    % if functions:
    <li><h3><a href="#header-functions">Functions</a></h3>
      ${show_column_list(functions)}
    </li>
    % endif

    % if classes:
    <li><h3><a href="#header-classes">Classes</a></h3>
      <ul>
      % for c in classes:
        <li>
        <h4><code>${link(c.refname)}</code></h4>
        <%
          methods = c.functions() + c.methods()
        %>
        % if methods:
          ${show_column_list(methods)}
        % endif
        </li>
      % endfor
      </ul>
    </li>
    % endif

    </ul>
  </nav>
</%def>

<!doctype html>
<html lang="${html_lang}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, minimum-scale=1" />
  <meta name="generator" content="pdoc ${pdoc.__version__}" />

  % if module_list:
    <title>Python module list</title>
    <meta name="description" content="A list of documented Python modules." />
  % else:
    <title>${module.name} API documentation</title>
    <meta name="description" content="${module.docstring | glimpse, trim, h}" />
  % endif

  <link href='https://cdnjs.cloudflare.com/ajax/libs/normalize/8.0.0/normalize.min.css' rel='stylesheet'>
  <link href='https://cdnjs.cloudflare.com/ajax/libs/10up-sanitize.css/8.0.0/sanitize.min.css' rel='stylesheet'>
  % if show_source_code:
    <link href="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/9.12.0/styles/github.min.css" rel="stylesheet">
  %endif

  <%namespace name="css" file="css.mako" />
  <style>${css.mobile()}</style>
  <style media="screen and (min-width: 700px)">${css.desktop()}</style>
  <style media="print">${css.print()}</style>

</head>
<body>
<main>
  % if module_list:
    <article id="content">
      ${show_module_list(modules)}
    </article>
  % else:
    <article id="content">
      ${show_module(module)}
    </article>
    ${module_index(module)}
  % endif
</main>

<footer id="footer">
    <p>Generated by <a href="https://github.com/mitmproxy/pdoc">pdoc ${pdoc.__version__}</a></p>
</footer>

% if show_source_code:
    <script src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/9.12.0/highlight.min.js"></script>
    <script>hljs.initHighlightingOnLoad()</script>
% endif
</body>
</html>
