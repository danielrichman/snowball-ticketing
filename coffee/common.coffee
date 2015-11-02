window.make_title = (page_title) ->
    if page_title
        return "#{page_title} - #{site_title}"
    else
        return site_title

window.set_title = (title) ->
    document.title = make_title title
