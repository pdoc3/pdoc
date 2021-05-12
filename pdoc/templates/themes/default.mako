## Imports
<%!
    from pdoc.html_helpers import minify_css
    
    # All CSS color variables are defined using tuples which represent:
    # ( "variable name", "default value", "dark mode value" )
    #
    # All non color values come in:
    # ( "variable name", "default value" )
    #
    # For clarity's sake, the following are abbreviations used
    # in variable nomenclature:
    #
    # - bg: background
    # - fc: font color

    colors = [
        ## Backgrounds
        ("--bg-highlight-color", "#FFEE99", "#3e4951"),
        ("--bg-default", "#FFFFFF", "#22282D"),
        ("--bg-code", "#EEEEEE", "#3e4951"),
        ("--bg-code-hover", "#e0e0e0", "#313b42"),
        
        ## Font Colors
        ("--fc-default", "#0F1A20", "#ACBAC7"),
        ("--fc-muted", "#666666", "#ACBAC7"),
        
        ## Anchor Colors
        ("--link-primary", "#005588", "#539bf5"),
        ("--link-hover", "#ee8822", "#abcdf9"),

        ## Misc colors
        ("--ident-primary", "#990000", "#539bf5"),
        ("--hr-default", "#666666", "#444d56"),

        ## Borders
        ("--bd-default", "#DDDDDD", "#444d56"),
        ("--bd-pre", "#DDDDDD", "#3e4951"),
        ("--bd-primary", "#666666", "#539bf5"),

        ## Admonition backgrounds
        ("--adm-note", "#abeeff", "rgba(65, 132, 288, 0.1)"),
        ("--adm-todo", "#ddffdd", "rgba(165, 255, 169, 0.1)"),
        ("--adm-warning", "#ffdd44", "rgba(255, 221, 68, 0.2)"),
        ("--adm-error", "#feb6c1", "rgba(254, 182, 193, 0.2)"),
        
        ## Admonition borders
        ("--adm-bd-note", "#abeeff", "#539bf5"),
        ("--adm-bd-todo", "#ddffdd", "#a5ffa9"),
        ("--adm-bd-warning", "#ffdd44", "#ffdd44"),
        ("--adm-bd-error", "#feb6c1", "#feb6c1"),
    ]

    default = [f"{color[0]}: {color[1]};" for color in colors]
    dark = [f"{color[0]}: {color[2]};" for color in colors]

    root_light = f":root[data-theme='theme-light'] {{{''.join(default)}}}"
    root_dark = f":root[data-theme='theme-dark'] {{{''.join(dark)}}}"
    root_light_auto = f"@media (prefers-color-scheme: light) {{ :root[data-theme='theme-light'] {{{''.join(default)}}} }}"
    root_dark_auto = f"@media (prefers-color-scheme: dark) {{ :root[data-theme='theme-dark'] {{{''.join(dark)}}} }}"

    color_variables = f"{root_light}{root_dark}{root_light_auto}{root_dark_auto}"
%>

## Theme
<%def name="style()" filter="minify_css">
    ${color_variables}
</%def>