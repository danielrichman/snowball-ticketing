$(document).ready ->
    # static display until the JS loads.
    # the css in extra-css is too specific
    $("#extra-css").remove()

    $("section")
        .addClass("item")
        .wrapAll("<div id='login-slider' class='carousel slide'>")
        .wrapAll("<div class='carousel-inner'>")

    slider = $("#login-slider")
    inner = slider.children(".carousel-inner")

    inner.height Math.max.apply null,
        for elem in $("section")
            $(elem).addClass "active"
            h = inner.height()
            $(elem).removeClass "active"
            h

    $("##{initial_section}").addClass "active"

    slider.carousel interval: false

    for id, options of history_sections
        options.instant_in = (elem) -> elem.addClass "active"
        options.instant_out = (elem) -> elem.removeClass "active"
        options.change_out = (elem) -> null
        options.change_in = (elem) -> slider.carousel elem.index()

    history_init initial_section, history_sections,
                 initial_section == "login-choices"
