-- Selwyn Snowball Ticketing
-- database schema; PostgreSQL
-- Daniel Richman djr61 2013

\set ON_ERROR_STOP

DROP TABLE IF EXISTS log;
DROP TYPE IF EXISTS log_level;
DROP TABLE IF EXISTS sessions;
DROP TABLE IF EXISTS tickets;
DROP TYPE IF EXISTS expires_reason;
DROP TABLE IF EXISTS tickets_settings;
DROP TYPE IF EXISTS tickets_settings_user_group;
DROP TYPE IF EXISTS tickets_settings_ticket_group;
DROP TYPE IF EXISTS tickets_settings_mode;
DROP TABLE IF EXISTS users;
DROP TYPE IF EXISTS person_type;
DROP TYPE IF EXISTS user_type;
DROP TABLE IF EXISTS colleges;
DROP FUNCTION IF EXISTS utcnow();

CREATE FUNCTION utcnow() RETURNS timestamp
    AS 'SELECT CURRENT_TIMESTAMP AT TIME ZONE ''UTC'''
    LANGUAGE SQL
    STABLE;

CREATE TABLE colleges (
    college_id integer NOT NULL PRIMARY KEY,

    -- instid must match jdCollege from lookup
    -- list of instids and names acquired from lookup;
    -- "child institutions of COLL" with some odd ones pruned
    instid varchar(10) NOT NULL UNIQUE CHECK (instid != ''),
    name varchar(100) NOT NULL UNIQUE CHECK (name != '')
);

INSERT INTO colleges (college_id, instid, name) VALUES
(0, 'CHRISTS', 'Christ''s College'),
(1, 'CHURCH', 'Churchill College'),
(2, 'CLARE', 'Clare College'),
(3, 'CLAREH', 'Clare Hall'),
(4, 'CORPUS', 'Corpus Christi College'),
(5, 'DARWIN', 'Darwin College'),
(6, 'DOWN', 'Downing College'),
(7, 'EMM', 'Emmanuel College'),
(8, 'FITZ', 'Fitzwilliam College'),
(9, 'GIRTON', 'Girton College'),
(10, 'CAIUS', 'Gonville and Caius College'),
(11, 'HOM', 'Homerton College'),
(12, 'HUGHES', 'Hughes Hall'),
(13, 'JESUS', 'Jesus College'),
(14, 'KINGS', 'King''s College'),
(15, 'LCC', 'Lucy Cavendish College'),
(16, 'MAGD', 'Magdalene College'),
(17, 'NEWH', 'Murray Edwards College'),
(18, 'NEWN', 'Newnham College'),
(19, 'PEMB', 'Pembroke College'),
(20, 'PET', 'Peterhouse'),
(21, 'QUEENS', 'Queens'' College'),
(22, 'ROBIN', 'Robinson College'),
(23, 'SEL', 'Selwyn College'),
(24, 'SID', 'Sidney Sussex College'),
(25, 'CATH', 'St Catharine''s College'),
(26, 'EDMUND', 'St Edmund''s College'),
(27, 'JOHNS', 'St John''s College'),
(28, 'TRIN', 'Trinity College'),
(29, 'TRINH', 'Trinity Hall'),
(30, 'WOLFC', 'Wolfson College');

CREATE TYPE person_type AS ENUM (
    'undergraduate',
    'postgraduate',
    'alumnus',
    'staff',
    'cam-other',
    'non-cam'
);

CREATE TYPE user_type AS ENUM (
    'raven',
    'password'
);

CREATE TABLE users (
    user_id SERIAL PRIMARY KEY,
    user_type user_type NOT NULL,

    surname varchar(50),
    othernames varchar(50),

    person_type person_type NOT NULL,
    college_id integer REFERENCES colleges (college_id),
    matriculation_year integer,
    crsid varchar(20) UNIQUE CHECK ( lower(crsid) = crsid ),

    -- details_from_lookup: refers to surname, college_id
    details_from_lookup boolean NOT NULL DEFAULT FALSE,
    -- user can't be used until details_completed is set;
    -- see constraints for requirements
    details_completed boolean NOT NULL DEFAULT FALSE,

    -- lowercase requirement intentional
    email varchar(100) NOT NULL UNIQUE
        CHECK ( email ~ E'^[a-z0-9._%+-]+@[a-z0-9.-]+\\.[a-z]{2,4}$' ),

    email_confirm_secret varchar(25),
    email_confirmed boolean NOT NULL DEFAULT FALSE,

    password_bcrypt varchar(100),

    pwreset_created timestamp,
    pwreset_secret varchar(25),
    pwreset_expires timestamp CHECK ( pwreset_expires >= pwreset_created ),

    enable_login boolean NOT NULL DEFAULT FALSE,

    hide_instructions boolean NOT NULL DEFAULT FALSE,
    last_receipt timestamp,

    notes text NOT NULL DEFAULT '',

    -- since they're both UNIQUE, we could have problems if someone signs up
    -- with a cam email and then tries to log in via Raven
    CONSTRAINT raven_users_exclusively_have_crsids
        CHECK ( (user_type = 'raven') = (crsid IS NOT NULL) ),
    CONSTRAINT raven_users_exclusively_have_cam_emails
        CHECK ( (lower(split_part(email, '@', 2)) = 'cam.ac.uk') =
                (user_type = 'raven') ),
    CONSTRAINT raven_users_have_confirmed_emails
        CHECK ( email_confirmed OR user_type != 'raven' ),
    CONSTRAINT raven_users_do_not_need_to_confirm_email
        CHECK ( email_confirm_secret IS NULL or user_type != 'raven' ),
    -- in 2013 the UCS added 'Raven for life' - alumni will still be able to
    -- log into Raven. Initially I wanted to use this, but it requires adding
    -- extra code to collect and confirm an email from alumni, since their
    -- crsid@cam address won't work. So for now, forbid that.
    CONSTRAINT raven_users_are_not_alumni
        CHECK ( person_type != 'alumnus' OR user_type != 'raven' ),
    CONSTRAINT details_completed_nonnulls
        CHECK ( (NOT details_completed) OR
                (surname IS NOT NULL AND othernames IS NOT NULL AND
                 email_confirmed) ),
    CONSTRAINT password_users_exclusively_have_passwords
        CHECK ( (user_type = 'password') = (password_bcrypt IS NOT NULL) ),
    CONSTRAINT pwreset_triplet
        CHECK ( (pwreset_secret IS NULL) = (pwreset_expires IS NULL) AND
                (pwreset_secret IS NULL) = (pwreset_created IS NULL) ),
    CONSTRAINT only_password_users_can_reset_password
        CHECK ( pwreset_secret IS NULL OR user_type = 'password' )
);

-- UNIQUE will create an index on each of "email" and "crsid"

CREATE TYPE tickets_settings_user_group AS ENUM
    ('all', 'members', 'alumni');

CREATE TYPE tickets_settings_ticket_group AS ENUM
    ('any', 'standard', 'vip');

-- precedence: closed > not-yet-open > available
-- not-yet-open is equivalent to closed except in the message shown.
-- i.e., tickets are available if all applicable rows have mode set to
-- available; and all user/types are closed if just all/any is set closed.
CREATE TYPE tickets_settings_mode AS ENUM
    ('not-yet-open', 'available', 'closed');

CREATE TABLE tickets_settings (
    who tickets_settings_user_group NOT NULL,
    what tickets_settings_ticket_group NOT NULL,

    quota integer CHECK ( quota >= 0 ),
    quota_met boolean,
    waiting_quota integer CHECK ( waiting_quota >= 0 ),
    waiting_quota_met boolean,
    -- the number until which a 'the waiting list is small' message will
    -- be displayed.
    waiting_smallquota integer CHECK ( waiting_smallquota >= 0),

    quota_per_person integer CHECK ( quota_per_person >= 0 ),
    quota_per_person_sentence text,

    mode tickets_settings_mode NOT NULL,
    price integer CHECK ( price >= 0 ),

    mode_sentence text,

    PRIMARY KEY (who, what),

    CONSTRAINT quota_pair
        CHECK ( (quota IS NULL) = (quota_met IS NULL) ),
    CONSTRAINT waiting_quota_pair
        CHECK ( (waiting_quota IS NULL) = (waiting_quota_met IS NULL) ),
    CONSTRAINT waiting_quotas_have_quota
        CHECK ( quota IS NOT NULL OR
                (waiting_quota IS NULL AND waiting_smallquota IS NULL) ),
    CONSTRAINT qpp_sentence_on_type_any_only
        CHECK ( what = 'any' OR quota_per_person_sentence IS NULL ),
    CONSTRAINT mode_sentence_on_all_any_only
        CHECK ( mode_sentence IS NULL OR (who = 'all' AND what = 'any'))
);

INSERT INTO tickets_settings
    (who, what, quota, quota_met, waiting_quota, waiting_quota_met,
     waiting_smallquota, quota_per_person, mode, price)
VALUES
--  who        what        quota        waiting q.  qpp         mode            price
   ('all',     'any',      850,  FALSE, NULL, NULL, 25,   10,   'not-yet-open', NULL),
   ('all',     'vip',      150,  FALSE, NULL, NULL, NULL, NULL, 'available',    NULL),

   ('members', 'any',      600,  FALSE, NULL, NULL, NULL, NULL, 'available',    NULL),
   ('alumni',  'any',      150,  FALSE, NULL, NULL, NULL, NULL, 'available',    NULL),

   ('members', 'standard', NULL, NULL,  NULL, NULL, NULL, NULL, 'available',    6900),
   ('members', 'vip',      NULL, NULL,  NULL, NULL, NULL, NULL, 'available',    7900),
   ('alumni',  'standard', NULL, NULL,  NULL, NULL, NULL, NULL, 'available',    7400),
   ('alumni',  'vip',      NULL, NULL,  NULL, NULL, NULL, NULL, 'available',    8400);
UPDATE tickets_settings
    SET quota_per_person_sentence = 'You may buy up to 10 tickets in total'
    WHERE who = 'all' AND what = 'any';

CREATE TYPE expires_reason AS ENUM
    ('not-finalised', 'not-paid', 'admin-intervention', 'other');

CREATE TABLE tickets (
    ticket_id SERIAL PRIMARY KEY,
    user_id integer NOT NULL REFERENCES users (user_id),

    -- unfortunately we end up storing this information twice for someone that
    -- buys a ticket for themselves. Could have had a 'people' table,
    -- and referenced it, but this is not really worth it - and would cause
    -- headaches if person A buys a ticket for person B and then person B
    -- logs in via Raven, thereby having a user created for them

    -- surname, othernames, person_type
    -- required to be non-null if finalised is set (below)
    surname varchar(50),
    othernames varchar(50),

    person_type person_type,
    college_id integer REFERENCES colleges (college_id),
    matriculation_year integer,

    vip boolean NOT NULL,
    waiting_list boolean NOT NULL,

    -- save the price of a ticket explicitly incase we give someone a
    -- free ticket, a discount, or later change the prices of tickets
    -- (and don't want to affect tickets already sold)
    -- value is integer pence
    price integer NOT NULL CHECK ( price >= 0 ),
    quota_exempt boolean NOT NULL DEFAULT FALSE,

    -- timezones are a huge PITA and source of bugs,
    -- especially since the clocks go back while we're selling tickets
    -- therefore, these are all timestamps without time zone and yeti's
    -- system timezone is UTC. If necessary, they can be converted to BST
    -- when displayed to the user.

    -- "finalised" being non-null implies that the ticket is finalised, etc.
    -- etc...

    -- finalised must be non-null if paid is set
    created timestamp NOT NULL,
    finalised timestamp CHECK ( finalised >= created ),
    paid timestamp CHECK ( paid >= finalised ),
    printed timestamp CHECK ( printed >= paid ),
    ticket_collected timestamp CHECK ( ticket_collected >= paid ),
    wristband_collected timestamp CHECK ( wristband_collected >= paid ),
    -- there's no constraint entered_ball >= ticket_collected and
    -- entered_ball >= wristband_collected, since they're quite vulnerable
    -- to human error and we don't want to screw up the entry. Having said
    -- that, it might be worth some warnings.
    entered_ball timestamp CHECK ( entered_ball >= paid ),

    -- expires is to implement the "you have 10 minutes to fill in the details
    -- of your tickets" thing.
    -- "expires" non null and <= utcnow() means the ticket is expired,
    expires timestamp,
    expires_reason expires_reason,

    entry_desk integer,
    forbid_desk_entry boolean NOT NULL DEFAULT FALSE,

    notes text NOT NULL DEFAULT '',
    desk_notes text NOT NULL DEFAULT '',

    CONSTRAINT finalised_tickets_have_details
        CHECK ( (finalised IS NULL) OR
            (surname IS NOT NULL AND
             othernames IS NOT NULL AND
             person_type IS NOT NULL) ),
    CONSTRAINT finalised_tickets_will_not_expire
        CHECK ( finalised IS NULL OR expires IS NULL ),
    CONSTRAINT paid_tickets_are_finalised
        CHECK ( paid IS NULL OR finalised IS NOT NULL ),
    CONSTRAINT paid_tickets_are_not_on_the_waiting_list
        CHECK ( paid IS NULL OR NOT waiting_list ),
    CONSTRAINT used_tickets_are_paid
        CHECK ( entered_ball IS NULL OR paid IS NOT NULL ),
    CONSTRAINT expires_pair
        CHECK ( (expires IS NULL) = (expires_reason IS NULL) ),
    CONSTRAINT entry_desk_pair
        CHECK ( (entry_desk IS NULL) = (entered_ball IS NULL) )
);

CREATE INDEX tickets_user_id_index ON tickets (user_id);

CREATE TABLE sessions (
    session_id SERIAL PRIMARY KEY,
    user_id integer NOT NULL REFERENCES users (user_id),
    secret varchar(25) NOT NULL,
    csrf_secret varchar(25) NOT NULL,
    ajax_secret varchar(25) NOT NULL,
    created timestamp NOT NULL,
    last timestamp NOT NULL,
    destroyed boolean NOT NULL DEFAULT FALSE
);

CREATE TYPE log_level AS ENUM
    ('debug', 'info', 'warning', 'error', 'critical');

CREATE TABLE log (
    record_id SERIAL PRIMARY KEY,
    created timestamp NOT NULL,
    level log_level NOT NULL,
    logger text NOT NULL,
    message text NOT NULL,
    function text NOT NULL,
    filename text NOT NULL,
    line_no integer NOT NULL,
    traceback text,

    request_path text,
    flask_endpoint text,
    remote_addr inet,

    -- sort of violate 2NF by having user_id here.
    -- there are some situations (immediately before creating a session)
    -- where user_id might be set and session_id not.
    -- also means we can have log_user_id_created_index which is a good thing
    -- don't foreign key constraints, since when creating a session we might
    -- start logging (via the log handler's connection) before the transaction
    -- for the request has been committed.
    session_id integer,
    user_id integer
);

CREATE INDEX log_created_index ON log (created);
CREATE INDEX log_session_id_created_index ON log (session_id, created);
CREATE INDEX log_user_id_created_index ON log (user_id, created);

-- don't allow modification of the colleges table
GRANT SELECT ON colleges TO "www-ticketing";


GRANT SELECT, INSERT, UPDATE, DELETE ON users TO "www-ticketing";
GRANT SELECT, UPDATE ON users_user_id_seq TO "www-ticketing";
GRANT SELECT, INSERT, UPDATE, DELETE ON tickets_settings TO "www-ticketing";
GRANT SELECT, INSERT, UPDATE, DELETE ON tickets TO "www-ticketing";
GRANT SELECT, UPDATE ON tickets_ticket_id_seq TO "www-ticketing";

-- allow creating, updating last, and destroying sessions via 'destroy'
GRANT SELECT, INSERT ON sessions TO "www-ticketing";
GRANT UPDATE ( last, destroyed ) ON sessions TO "www-ticketing";
GRANT SELECT, UPDATE ON sessions_session_id_seq TO "www-ticketing";

-- add and view only
GRANT SELECT, INSERT ON log TO "www-ticketing";
GRANT SELECT, UPDATE ON log_record_id_seq TO "www-ticketing";

-- backups
GRANT SELECT ON ALL TABLES IN SCHEMA PUBLIC TO "yocto-pgdump";
GRANT SELECT ON ALL SEQUENCES IN SCHEMA PUBLIC TO "yocto-pgdump";
