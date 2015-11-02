$(document).ready ->
    {url, value} = tickets_hide_instructions
    container = (o) -> $(o).parents(".tickets-instructions").first()

    $(".tickets-instructions-hide button").click (event) ->
        event.preventDefault()
        container(this).addClass("collapsed")

        checkbox = $(this).parent().find("input[name='hide_instructions']")
        if checkbox.prop("checked") and not value
            checkbox.parent().hide()
            $.ajax
                url: url
                type: "POST"
                data:
                    ajax_secret: window.ajax_secret

        return

    $(".tickets-instructions-show button").click (event) ->
        event.preventDefault()
        container(this).removeClass("collapsed")
        return
