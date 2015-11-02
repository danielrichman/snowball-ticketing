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

current_section = null
static_section = null
sections = null
url_map = {}
history_enable = null
hash_enable = null

log = (msg) -> console?.log? "history.coffee: #{msg}"

change = (to, animation="change") ->
    if current_section == to
        log "change nop - already at #{to}"
        return

    from = sections[current_section]
    to = sections[to]

    from["#{animation}_out"] $("##{from.id}")
    to["#{animation}_in"] $("##{to.id}")
    set_title to.title
    current_section = to.id
    return

page_load = ->
    if history_enable
        $(window).bind "popstate", ->
            log "popstate '#{location.pathname}'"

            id = url_map[location.pathname]
            if id?
                log "popstate - changing to #{id}"
                change id
            else
                log "popstate - unknown section, no action"

    else if hash_enable
        $(window).bind "hashchange", ->
            log "hashchange #{location.hash}"
            if location.hash == ""
                id = static_section
            else
                id = location.hash[2..]
            if sections[id]?
                change id
            return

        if location.hash
            log "hash (load) '#{location.hash}'"

        if location.hash[...2] == "#!"
            id = location.hash[2..]
            if sections[id]?
                log "hash (load) found #!, instant change to #{id}"
                change id, "instant"
            else
                log "hash (load) unknown section - no action"

    return

hook_links = ->
    for elem in $("a")
        do ->
            a_href = $(elem).attr('href')
            a_id = url_map[a_href]

            if a_id?
                $(elem).click (event) ->
                    if history_enable
                        title = sections[a_id].title
                        log "click - pushing state '#{title}' #{a_href}"
                        history.pushState null, title, a_href

                    else if hash_enable
                        log "click - setting hash #{a_id}"
                        location.hash = "!#{a_id}"

                    log "click - changing to #{a_id} (#{a_href})"
                    change a_id
                    # TODO ga 'send', 'pageview', a_href

                    event.preventDefault()
                    return undefined

# static_section - the section made visible by HTML/CSS, corresponding to the
#   URL / the document that was fetched from the server
# sections - map, section id -> object with optional properties
#   title: string
#   change_in,change_out: (jquery elem) ->
#       transition this section in/out
#   instant_in,instant_out: (jquery elem) ->
#       instant transition (used when a hash is found after page load)
# allow_hash - can we use #hash history in HTML4 browsers?
#   typically used to only allow #!hash history on the main page
#   thereby avoiding /sectiona#!sectionb
window.history_init = (static_section_, sections_, allow_hash) ->
    current_section = static_section = static_section_
    sections = sections_

    defaults =
        title: window.document.title
        instant_out: (elem) -> elem.hide()
        instant_in: (elem) -> elem.show()
        change_out: (elem) -> elem.hide()
        change_in: (elem) -> elem.show()

    for id, options of sections
        extra =
            title: options.title
            id: id
        sections[id] = $.extend {}, defaults, options, extra

        if not sections[id].url?
            throw "history: url not specified in section #{id}"
        url_map[sections[id].url] = id

    history_enable =
        !!( window.onpopstate != undefined && window.history?.pushState )
    hash_enable =
        !!( !history_enable && allow_hash &&
            location.hash != undefined && window.onhashchange != undefined )

    log "init static_section=#{static_section} " +
        "sections=[#{(id for id, _ of sections).join ', '}] " +
        "allow_hash=#{allow_hash}"

    log "detect history_enable=#{history_enable} hash_enable=#{hash_enable}"

    page_load()
    if history_enable or hash_enable
        hook_links()
    else
        log "disabled - not hooking links"

    return
