#!/usr/bin/env python

import datetime
import math
import pkg_resources

from genshi.builder import tag
from trac.core import *
from trac.ticket import model
from trac.web import IRequestHandler
from trac.web.chrome import INavigationContributor, ITemplateProvider, \
                            add_script, add_script_data
from trac.perm import IPermissionRequestor
from trac.util.datefmt import to_utimestamp, utc
from trac.util.translation import _


class TicketGraphModule(Component):
    implements(IPermissionRequestor, IRequestHandler, INavigationContributor, ITemplateProvider)

    # IPermissionRequestor methods
    def get_permission_actions(self):
        return ['TICKET_GRAPH']

    # INavigationContributor methods
    def get_active_navigation_item(self, req):
        return 'ticketgraph'

    def get_navigation_items(self, req):
        if 'TICKET_GRAPH' in req.perm:
            yield ('mainnav', 'ticketgraph',
                   tag.a(_('Ticket Graph'), href=req.href.ticketgraph()))

    # ITemplateProvider methods
    def get_htdocs_dirs(self):
        return [('ticketgraph', pkg_resources.resource_filename(__name__, 'htdocs'))]

    def get_templates_dirs(self):
        return [pkg_resources.resource_filename(__name__, 'templates')]

    # IRequestHandler methods
    def match_request(self, req):
        return req.path_info == '/ticketgraph'

    def process_request(self, req):
        req.perm.require('TICKET_GRAPH')

        days = int(req.args.get('days', 90))
        component = req.args.get('component', '')

        # These are in microseconds; the data returned is in milliseconds
        # because it gets passed to flot

        today = datetime.datetime.combine(datetime.date.today(), datetime.time(tzinfo=utc))
        ts_start = to_utimestamp(today - datetime.timedelta(days=days))
        ts_end = to_utimestamp(today + datetime.timedelta(days=1))

        db = self.env.get_read_db()
        cursor = db.cursor()

        if component:
            cursor.execute('SELECT c.name FROM component c WHERE c.name = %s', (component,))
            if not cursor.fetchone():
                component = ''

        series = {
            'openedTickets': {},
            'closedTickets': {},
            'openTickets': {},
            'reopenedTickets': {}
        }

        if component:
            # number of created tickets for the time period, grouped by day (ms)
            cursor.execute('SELECT COUNT(DISTINCT id), CAST(time / 86400000000 as integer) * 86400000 ' \
                           'AS date FROM ticket WHERE time >= %s AND component = %s' \
                           'GROUP BY date ORDER BY date ASC', (ts_start, component))
            for count, timestamp in cursor:
                series['openedTickets'][float(timestamp)] = float(count)

            # number of reopened tickets for the time period, grouped by day (ms)
            cursor.execute('SELECT COUNT(DISTINCT ticket), CAST(tc.time / 86400000000 as integer) * 86400000 ' \
                           'AS date FROM ticket_change tc INNER JOIN ticket t ON tc.ticket = t.id ' \
                           'WHERE field = \'status\' AND newvalue = \'reopened\' ' \
                           'AND tc.time >= %s ' \
                           'AND t.component = %s ' \
                           'GROUP BY date ORDER BY date ASC', (ts_start, component))
            for count, timestamp in cursor:
                series['reopenedTickets'][float(timestamp)] = float(count)

            # number of closed tickets for the time period, grouped by day (ms)
            cursor.execute('SELECT COUNT(DISTINCT ticket), CAST(tc.time / 86400000000 as integer) * 86400000 ' \
                           'AS date FROM ticket_change tc INNER JOIN ticket t ON tc.ticket = t.id ' \
                           'WHERE field = \'status\' AND newvalue = \'closed\' ' \
                           'AND tc.time >= %s ' \
                           'AND t.component = %s ' \
                           'GROUP BY date ORDER BY date ASC', (ts_start, component))
            for count, timestamp in cursor:
                series['closedTickets'][float(timestamp)] = float(count) * -1

        else:
            # number of created tickets for the time period, grouped by day (ms)
            cursor.execute('SELECT COUNT(DISTINCT id), CAST(time / 86400000000 as integer) * 86400000 ' \
                           'AS date FROM ticket WHERE time >= %s ' \
                           'GROUP BY date ORDER BY date ASC', (ts_start,))
            for count, timestamp in cursor:
                series['openedTickets'][float(timestamp)] = float(count)

            # number of reopened tickets for the time period, grouped by day (ms)
            cursor.execute('SELECT COUNT(DISTINCT ticket), CAST(time / 86400000000 as integer) * 86400000 ' \
                           'AS date FROM ticket_change WHERE field = \'status\' AND newvalue = \'reopened\' ' \
                           'AND time >= %s ' \
                           'GROUP BY date ORDER BY date ASC', (ts_start,))
            for count, timestamp in cursor:
                series['reopenedTickets'][float(timestamp)] = float(count)

            # number of closed tickets for the time period, grouped by day (ms)
            cursor.execute('SELECT COUNT(DISTINCT ticket), CAST(time / 86400000000 as integer) * 86400000 ' \
                           'AS date FROM ticket_change WHERE field = \'status\' AND newvalue = \'closed\' ' \
                           'AND time >= %s ' \
                           'GROUP BY date ORDER BY date ASC', (ts_start,))
            for count, timestamp in cursor:
                series['closedTickets'][float(timestamp)] = float(count) * -1

        # number of open tickets at the end of the reporting period
        cursor.execute('SELECT COUNT(*) FROM ticket WHERE status <> \'closed\'')

        open_tickets = cursor.fetchone()[0]
        open_ts = math.floor(ts_end / 1000)

        while open_ts >= math.floor(ts_start / 1000):
            if open_ts in series['closedTickets']:
                open_tickets -= series['closedTickets'][open_ts]
            if open_ts in series['openedTickets']:
                open_tickets -= series['openedTickets'][open_ts]
            if open_ts in series['reopenedTickets']:
                open_tickets -= series['reopenedTickets'][open_ts]

            series['openTickets'][open_ts] = open_tickets
            open_ts -= 86400000

        components = model.Component.select(self.env)

        data = {}
        for i in series:
            keys = series[i].keys()
            keys.sort()
            data[i] = [(k, series[i][k]) for k in keys]

        add_script(req, 'ticketgraph/jquery.flot.min.js')
        add_script(req, 'ticketgraph/jquery.flot.stack.min.js')
        add_script(req, 'ticketgraph/ticketgraph.js')
        add_script_data(req, data)

        return 'ticketgraph.html', {'days': days, 'component': component, 'components': components}, None
