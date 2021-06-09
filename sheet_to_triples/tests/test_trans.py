# Copyright 2021 Visual Meaning Ltd
# This is free software licensed as GPL-3.0-or-later - see COPYING for terms.

"""Unittests for the trans.py modules of sheet-to-triples."""

import copy
import unittest

from unittest import mock
from .. import trans


def _mock_open(data):
    return mock.patch('builtins.open', mock.mock_open(read_data=data))


def _mock_env():
    return mock.patch('os.getenv', return_value='test_transforms')


class TransformTestCase(unittest.TestCase):

    def test_init(self):
        details = {'book': 'test_book.xlsx', 'sheet': 'test_sheet'}
        transform = trans.Transform('test', details)
        self.assertEqual(transform.name, 'test')
        self.assertEqual(transform.book, 'test_book.xlsx')
        self.assertEqual(transform.sheet, 'test_sheet')

    def test_cannot_init_with_bad_details(self):
        with self.assertRaises(AttributeError):
            trans.Transform('test', {'no_slot_for_this': 'nonexistent'})

    def test_iter_from_name(self):
        strdetails = '{"allow_empty_subject": True}'
        with _mock_open(strdetails) as mock_open, _mock_env():
            transform = next(trans.Transform.iter_from_name('test'))

        self.assertIsInstance(transform, trans.Transform)
        self.assertEqual(transform.allow_empty_subject, True)
        mock_open.assert_called_once_with(
            'test_transforms/test.py', 'r', encoding='utf-8'
        )

    def test_iter_from_name_with_base_path(self):
        strdetails = '{"allow_empty_subject": True}'
        with _mock_open(strdetails) as mock_open, _mock_env() as mock_env:
            next(trans.Transform.iter_from_name(
                'test', base_path='/different/path'
            ))

        mock_open.assert_called_once_with(
            '/different/path/test.py', 'r', encoding='utf-8'
        )
        mock_env.assert_not_called()

    def test_iter_from_name_transform_list(self):
        transform = ('[{"allow_empty_subject": True},'
                     '{"allow_empty_subject": False}]')

        with _mock_open(transform), _mock_env():
            transforms = [t for t in trans.Transform.iter_from_name('test')]

        for t in transforms:
            self.assertIsInstance(t, trans.Transform)

        self.assertEqual(
            [t.allow_empty_subject for t in transforms],
            [True, False]
        )

    def test_get_non_uniques(self):
        details = {'non_unique': ['http://a', 'http://b']}
        transform = trans.Transform('test', details)

        self.assertEqual(
            transform.get_non_uniques('test-namespace'),
            {'http://a', 'http://b'}
        )

    def test_uses_sheet(self):
        transform = trans.Transform('test', {'sheet': 'test_sheet'})
        self.assertTrue(transform.uses_sheet())

    def test_uses_sheet_defaults_false(self):
        self.assertFalse(trans.Transform('test', {}).uses_sheet())

    def test_required_rows(self):
        details = {
            'lets': {
                'testvar': 'prefix_{row[column_1]}',
                'nonevar': 'no_row_reference',
            },
            'triples': [
                ('{testvar}', 'predicate', '{row[column_2]}')
            ]
        }
        transform = trans.Transform('test', details)
        self.assertEqual(
            transform.required_rows(),
            {'column_1', 'column_2'}
        )

    def test_required_rows_empty(self):
        self.assertFalse(trans.Transform('test', {}).required_rows())

    @unittest.skip
    def test_prepare_queries(self):
        # unsure how to test this
        pass

    def test_prepare_queries_no_queries(self):
        self.assertEqual(
            trans.Transform('test', {}).prepare_queries('dummy'),
            {}
        )

    def _process_and_assertEqual(self, details, expected):
        rows = trans.Transform('test', details).process({}, details['data'])
        str_rows = [[str(x) for x in r] for r in rows]
        self.assertEqual(str_rows, expected)

    def test_process(self):
        # as we don't care about the internal functioning of rdf in these
        # tests, we want to just have it return what we give it without
        # any custom prefix behaviour, which means prepending http://
        # to subject and predicate values
        details = {
            'data': [
                {'col1': 'http://a', 'col2': '1'},
                {'col1': 'http://b', 'col2': '2'}
            ],
            'lets': {
                'iri': '{row[col1]}_iri'
            },
            'triples': [
                ('{iri}', 'http://predicate', '{row[col2]}'),
            ]
        }
        expected = [
            ['http://a_iri', 'http://predicate', '1'],
            ['http://b_iri', 'http://predicate', '2'],
        ]
        self._process_and_assertEqual(details, expected)

    def test_process_lets_cannot_bind(self):
        details = {
            'data': [
                {'col1': 'http://a', 'col2': '1'},
            ],
            'lets': {
                'iri': '{row[col1]}_iri',
                'output_iri': '{row[col3]}_iri'
            },
            'triples': [
                ('{iri}', 'http://predicate', '{output_iri}'),
            ]
        }
        # should default to emptystring
        expected = [
            ['http://a_iri', 'http://predicate', ''],
        ]
        self._process_and_assertEqual(details, expected)

    SUBJ_DETAILS = {
            'data': [
                {'col1': 'http://a', 'col2': '1'},
                {'col2': '2'},
            ],
            'lets': {
                'iri': '{row[col1]}_iri',
            },
            'triples': [
                ('{iri}', 'http://predicate', '{row[col2]}'),
            ]
        }

    def test_process_no_subj(self):
        details = copy.deepcopy(self.SUBJ_DETAILS)
        rows = trans.Transform('test', details).process({}, details['data'])
        with self.assertRaises(ValueError):
            # need to unpack from generator to trigger error
            [x for x in rows]

    def test_process_allow_empty_subject(self):
        details = copy.deepcopy(self.SUBJ_DETAILS)
        details['allow_empty_subject'] = True
        # should ignore row with empty subject and not throw ValueError
        expected = [
            ['http://a_iri', 'http://predicate', '1']
        ]
        self._process_and_assertEqual(details, expected)

    OBJ_DETAILS = {
        'data': [
            {'col1': 'http://a', 'col2': '1'},
            {'col1': 'http://b'},
        ],
        'lets': {
            'iri': '{row[col1]}_iri',
        },
        'triples': [
            ('{iri}', 'http://predicate', '{row[col2]}'),
        ]
    }

    def test_process_no_obj(self):
        details = copy.deepcopy(self.OBJ_DETAILS)
        expected = [
            ['http://a_iri', 'http://predicate', '1']
        ]
        self._process_and_assertEqual(details, expected)

    def test_process_no_obj_allow_empty_subject(self):
        details = copy.deepcopy(self.OBJ_DETAILS)
        details['allow_empty_subject'] = True
        expected = [
            ['http://a_iri', 'http://predicate', '1']
        ]
        self._process_and_assertEqual(details, expected)

    @unittest.skip
    def test_process_query_map(self):
        # unsure how to test this
        pass