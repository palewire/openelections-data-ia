#!/usr/bin/env python

"""Parse 2013 county-level general election results"""

import csv
import re

from openelexdata.us.ia import arg_parser
from openelexdata.us.ia import BaseParser, ParserState
from openelexdata.us.ia.util import get_column_breaks, split_into_columns 


office_re = re.compile(r'State (Senator|Representative)')
district_re = re.compile(r'District (?P<district_num>\d+)')
whitespace_re = re.compile(r'\s{2,}')
party_re = re.compile(r'(Republican|Democratic|Constitution|Iowa Green|'
    'Libertarian|Socialism|Liberation|Socialist|Workers|Nominated|Petition|Party)'
    '\s{0,1}(and|by|)\s{0,1}(Party|)\s*(for|)')

def matches_page_header(line):
    return line == "IOWA SECRETARY OF STATE"

class RootState(ParserState):
    name = 'root'

    def handle_line(self, line):
        if matches_page_header(line):
            self._context.change_state('page_header')
        elif office_re.match(line):
            self._context.change_state('contest_header')

class PageHeader(ParserState):
    name = 'page_header'

    def handle_line(self, line):
        if "ELECTION CANVASS SUMMARY" in line:
            self._context.change_state('root')

class ContestHeader(ParserState):
    name = 'contest_header'

    def enter(self):
        self._context['office'] = None
        self._context['district_num'] = None
        self.handle_line(self._context.current_line)

    def handle_line(self, line):
        if line == "":
            if self._context['office']:
                self._context.change_state('results_header')

            return

        m = office_re.match(line)
        if m:
            self._context['office'] = line 
            return

        m = district_re.match(line)
        if m:
            self._context['district_num'] = m.group('district_num')
            self._context.change_state('results_header')

class ResultsHeader(ParserState):
    name = 'results_header'

    def enter(self):
        self.header_lines = []

    def handle_line(self, line):
        if line == "" and len(self.header_lines) > 1:
            self._context.change_state('results') 
            return

        if line:
            self.header_lines.append(self._context.raw_line)

    def exit(self):
        candidates, parties = self.parse_header_lines(self.header_lines)
        self._context['candidates'] = candidates
        self._context['parties'] = parties

    def parse_header_lines(self, lines):
        breaks = get_column_breaks(lines)
        parsed_lines = split_into_columns(lines, breaks)
        candidates = ["" for i in range(len(parsed_lines[0]))]
        parties = ["" for i in range(len(parsed_lines[0]))]
        for cols in parsed_lines:
            for i in range(len(cols)):
                col = cols[i]
                m = party_re.match(col)
                if m:
                    collection = parties
                else:
                    collection = candidates

                if collection[i] and col:
                    collection[i] += " "

                collection[i] += col

        return candidates, parties


class Results(ParserState):
    name = 'results'

    def handle_line(self, line):
        if line == "":
            return
        
        cols = whitespace_re.split(line)

        assert len(cols) == len(self._context['candidates']) + 2

        for i in range(2, len(cols)):
            self._context.results.append({
                'office': self._context['office'], 
                'district': self._context['district_num'],
                'candidate': self._context['candidates'][i-2],
                'party': self._context['parties'][i-2],
                'reporting_level': "county", 
                'jurisdiction': cols[0], 
                'votes': cols[i].replace(',', ''), 
            })

        if cols[0] == "Total":
            self._context.change_state('root')


class ResultParser(BaseParser):
    def __init__(self, infile):
        super(ResultParser, self).__init__(infile)
        self._register_state(RootState(self))
        self._register_state(PageHeader(self))
        self._register_state(ContestHeader(self))
        self._register_state(ResultsHeader(self))
        self._register_state(Results(self))
        self._current_state = self._get_state('root')


fields = [
    'office',
    'district',
    'candidate',
    'party',
    'reporting_level',
    'jurisdiction',
    'votes',
]

if __name__ == "__main__":
    args = arg_parser.parse_args()

    parser = ResultParser(args.infile)
    writer = csv.DictWriter(args.outfile, fields)
    try:
        parser.parse()
    except Exception:
        msg = "Exception at line {} of input file, in state {}\n"
        print(msg.format(parser.line_number, parser.current_state.name))
        print("Line: {}".format(parser.current_line))
        raise

    writer.writeheader()
    for result in parser.results:
        writer.writerow(result)
