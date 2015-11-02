# Copyright 2013 Daniel Richman
#
# This file is part of The Snowball Ticketing System.
#
# The Snowball Ticketing System is free software: you can redistribute it
# and/or modify it under the terms of the GNU General Public License as
# published by the Free Software Foundation, either version 3 of the License,
# or (at your option) any later version.
#
# The Snowball Ticketing System is distributed in the hope that it will be
# useful, but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with The Snowball Ticketing System.  If not, see
# <http://www.gnu.org/licenses/>.

log = (msg) -> console?.log? "deadline.coffee: #{msg}"

$(document).ready ->
    if deadline_settings is null
        return

    {elem, time, url} = deadline_settings
    elem = $(elem)
    deadline_time = time

    log "setup #{deadline_time}"

    $.ajax
        url: url
        cache: false
        success: (data) ->
            server_time = data.time
            relative = deadline_time - server_time

            log "server time #{server_time}, relative deadline #{relative}"

            minutes = Math.floor(relative / 60)
            seconds = relative % 60

            update = ->
                hours = Math.floor(minutes / 60)
                days = Math.floor(hours / 24)
                weeks = Math.floor(days / 7)

                elem.text(
                    if days > 1
                        "#{days} days remain."
                    else if hours > 1
                        "#{hours} hours remain."
                    else if minutes > 1
                        "#{minutes} minutes remain."
                    else if minutes == 1
                        "1 minute remains."
                    else
                        "Under a minute remains."
                )
                if minutes <= 1
                    elem.addClass "imminent"

            tick = ->
                minutes--
                update()
                setTimeout(tick, 60 * 1000)
                return

            update()

            log "minutes #{minutes}, first tick in #{seconds} seconds"
            setTimeout(tick, seconds * 1000)
            return

    return
