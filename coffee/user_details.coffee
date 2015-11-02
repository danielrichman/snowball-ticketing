$(document).ready ->
    resending = false
    link = $("#email-confirm-resend")
    alert = $("#email-confirm-alert")
    url = link.attr("href")

    set_text = (class_, body) ->
        if class_ != "muted"
            class_ = "text-" + class_
        new_ = $("<span class='#{class_}'>#{body}</span>")
        link.replaceWith new_
        link = new_

    link.click (event) ->
        event.preventDefault()
        if resending
            return
        resending = true

        set_text "muted", link.text()

        $.ajax
            url: url
            type: "POST"
            data:
                ajax_secret: window.ajax_secret
            success: (data) ->
                if data == 'OK'
                    set_text 'success', 'Sent.'
                else if data == 'ALREADY CONFIRMED'
                    alert.remove()
                else
                    set_text 'error', 'Error.'
                return
            error: ->
                set_text 'error', 'Error.'
                return

        return

$(document).ready ->
    {surname, othernames} = name_preview

    # ie8 doesn't have String.trim :-(

    if othernames.final
        get_othernames = -> othernames.value
    else
        get_othernames = -> jQuery.trim $("input#othernames").val()

    if surname.final
        get_surname = -> surname.value
    else
        get_surname = -> jQuery.trim $("input#surname").val()

    preview_parent = $(".name-preview")
    preview = $(".name-preview-value")

    update = ->
        a = get_othernames()
        b = get_surname()
        if a != "" and b != ""
            preview.text(a + " " + b)
            preview_parent.removeClass "hide"
        else
            preview_parent.addClass "hide"

        return

    $("input#othernames").change update
    $("input#surname").change update

    return
