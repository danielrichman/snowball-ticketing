old_set_title = window.set_title

window.set_title = (title) ->
    $("#page-title").text title
    old_set_title title
