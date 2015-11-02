$(document).ready ->
    $(".tickets-buy form").each ->
        form = $(this)

        buy_number = form.find("input.buy_number")
        buy_number.change ->
            p = if parseInt($(this).val()) != 1 then 's' else ''
            form.find(".buy_number-plural").text p
            return
        buy_number.change()

        return
