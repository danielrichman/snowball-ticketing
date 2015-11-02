$(document).ready ->
    cls = (val) -> "person-type-#{val or 'none'}"

    for ticket_id in unfinalised_ticket_ids
        do (ticket_id) ->
            person_type = $("select##{ticket_id}_person_type")
            fieldset = $("fieldset#ticket_#{ticket_id}")
            form_person_type = $("input##{ticket_id}_form_person_type")

            u = ->
                person_type.find("option").each ->
                    v = $(this).val()
                    fieldset.removeClass cls v
                fieldset.addClass cls person_type.val()
                form_person_type.val person_type.val()
                return

            person_type.change u
            u()
            return

$(document).ready ->
    for ticket_id in unfinalised_ticket_ids
        do (ticket_id) ->
            # as in user_details.coffee           
            othernames =
                input: $("input##{ticket_id}_othernames")
                get: -> jQuery.trim othernames.input.val()
            surname =
                input: $("input##{ticket_id}_surname")
                get: -> jQuery.trim surname.input.val()

            preview_parent = $("#ticket_#{ticket_id} .name-preview")
            preview = $("#ticket_#{ticket_id} .name-preview-value")

            update = ->
                a = othernames.get()
                b = surname.get()
                if a != "" and b != ""
                    preview.text(a + " " + b)
                    preview_parent.removeClass "hide"
                else
                    preview_parent.addClass "hide"

                return

            othernames.input.change update
            surname.input.change update
            update()

            return
    return
