# Copyright 2021 Visual Meaning Ltd
# This is free software licensed as GPL-3.0-or-later - see COPYING for terms.

"""Unittests for the run.py module of sheet-to-triples."""

import json
import unittest

import rdflib

from unittest import mock

from .. import run, trans


def _mock_open(data):
    return mock.patch('builtins.open', mock.mock_open(read_data=data))


def _mock_basename():
    return mock.patch(
        'os.path.basename',
        side_effect=lambda x: '/basename/' + x,
    )


def _mock_xl_lb():
    return mock.patch(
        'sheet_to_triples.xl.load_book',
        side_effect=lambda x: '/load_book/' + x,
    )


def _mock_xl_is(test_iter):
    return mock.patch(
        'sheet_to_triples.xl.iter_sheet',
        return_value=test_iter
    )


class TestArgs:
    """Stub class with attribute values matching args keys."""
    def __init__(self, args):
        for arg in args:
            setattr(self, arg, args[arg])


class TestRunner:
    """Initialise a Runner with some stub values as defaults."""
    # used where default values are relatively unimportant - they can be
    # selectively overridden when calling get_runner if they are important

    def __init__(self):
        model = {
            'terms': [
                {'subj': 'test_subj', 'pred': 'test_pred', 'obj': 'test_obj'}
            ]
        }
        self.args = {
            'books': ['test_book1.xlsx'],
            'model': model,
            'purge_except': lambda x: True,
            'resolve_same': False,
            'verbose': False,
        }

    def get_runner(self, args={}):
        return run.Runner(**{**self.args, **args})


class RunnerTestCase(unittest.TestCase):

    def test_from_args(self):
        model = {
            'terms': [
                {'subj': 'test_subj', 'pred': 'test_pred', 'obj': 'test_obj'}
            ]
        }
        argvalues = {
            'book': ['test_book1.xlsx', 'test_book2.xlsx'],
            'model': 'model.json',
            'purge_except': lambda x: True,
            'resolve_same': False,
            'verbose': False,
        }
        args = TestArgs(argvalues)
        model_data = json.dumps(model)
        with _mock_basename(), _mock_xl_lb(), _mock_open(model_data):
            runner = run.Runner.from_args(args)
        expected_books = {
            '/basename/test_book1.xlsx': '/load_book/test_book1.xlsx',
            '/basename/test_book2.xlsx': '/load_book/test_book2.xlsx',
        }
        self.assertEqual(runner.books, expected_books)
        self.assertEqual(runner.model, model)
        self.assertEqual(runner.non_unique, set())
        self.assertEqual(runner.resolve_same, False)
        self.assertEqual(runner.verbose, False)
        self.assertIsInstance(runner.graph, rdflib.graph.Graph)

    def test_use_non_uniques(self):
        transforms = [
            trans.Transform('test1', {'non_unique': ['http://a']}),
            trans.Transform('test2', {'non_unique': ['http://b']}),
        ]
        runner = TestRunner().get_runner()
        runner.use_non_uniques(transforms)
        self.assertEqual(runner.non_unique, {'http://a', 'http://b'})

    def test_set_terms(self):
        triples = [('new_test_subj', 'new_test_pred', 'new_test_obj')]
        runner = TestRunner().get_runner()
        runner.set_terms(triples)

        expected = [
            {
                    'subj': 'new_test_subj',
                    'pred': 'new_test_pred',
                    'obj': 'new_test_obj',
            }
        ]
        self.assertEqual(runner.model['terms'], expected)

    def test_run_model_changes(self):
        details = {
            'data': [
                {'col1': 'http://a', 'col2': '1'},
                {'col1': 'http://b', 'col2': '2'},
                {'col1': 'http://b', 'col2': '2'}
            ],
            'lets': {
                'iri': '{row[col1]}_iri'
            },
            'triples': [
                ('{iri}', 'http://pred', '{row[col2]}'),
            ]
        }
        transform = trans.Transform('test', details)

        # overwrite default terms as we want to test them
        args = {
            'model': {
                'terms': [
                    {'subj': 'a', 'pred': 'b', 'obj': 'c'}
                ]
            }
        }
        runner = TestRunner().get_runner(args)

        runner.run([transform])

        # should have default value + derived rows from details
        # also should have duplicate row in details['data'] removed
        expected_terms = [
            {'subj': 'a', 'pred': 'b', 'obj': 'c'},
            {'subj': 'http://a_iri', 'pred': 'http://pred', 'obj': '1'},
            {'subj': 'http://b_iri', 'pred': 'http://pred', 'obj': '2'},
        ]
        self.assertEqual(runner.model, {'terms': expected_terms})

    def test_run_non_unique_updated(self):
        details = {
            'non_unique': ['http://pred']
        }
        transform = trans.Transform('test', details)
        runner = TestRunner().get_runner()
        runner.run([transform])
        self.assertEqual(runner.non_unique, {'http://pred'})

    def _create_row_iter(self, rows):
        row_iter = []
        for row in rows:
            row_iter.append([TestArgs({'value': v}) for v in row])
        return row_iter

    def test_run_with_book(self):
        details = {
            'book': 'test_book1.xlsx',
            'sheet': 'test_sheet.xlsx',
            'triples': [
                ('http://{row[col1]}_iri', 'http://pred', '{row[col2]}'),
            ]
        }
        transform = trans.Transform('test', details)

        # fake book data for our mock iter_sheet function to return
        rows = [('col1', 'col2'), ('a', 'b'), ('', '')]
        row_iter = self._create_row_iter(rows)

        args = {
            'books': {
                'test_book1.xlsx': 'book object'
            },
            'model': {
                'terms': []
            }
        }
        runner = TestRunner().get_runner(args)

        with _mock_xl_is(row_iter) as mis:
            runner.run([transform])

        expected_terms = [
            {'subj': 'http://a_iri', 'pred': 'http://pred', 'obj': 'b'},
            {'subj': 'http://col1_iri', 'pred': 'http://pred', 'obj': 'col2'},
        ]
        self.assertEqual(runner.model, {'terms': expected_terms})
        mis.assert_called_once_with(['book object'], 'test_sheet.xlsx')

    def test_run_with_sheet_but_no_book(self):
        details = {
            'sheet': 'test_sheet.xlsx',
            'triples': [
                ('http://{row[col1]}_iri', 'http://pred', '{row[col2]}'),
            ]
        }
        transform = trans.Transform('test', details)

        rows = [('col1', 'col2'), ('', '')]
        row_iter = self._create_row_iter(rows)

        args = {
            'books': {
                'test_book1.xlsx': 'book object1',
                'test_book2.xlsx': 'book object2',
            },
            'model': {
                'terms': []
            }
        }
        runner = TestRunner().get_runner(args)

        with _mock_xl_is(row_iter) as mis:
            runner.run([transform])

        # should pass full list of book objects to iter_sheet
        mis.assert_called_once
        self.assertEqual(
            list(mis.call_args.args[0]),
            ['book object1', 'book object2'],
        )

    def test_run_error_if_no_matching_book(self):
        details = {
            'book': 'test_book2.xlsx',
            'sheet': 'test_sheet.xlsx',
        }
        transform = trans.Transform('test', details)

        rows = [('col1', 'col2'), ('', '')]
        row_iter = self._create_row_iter(rows)

        args = {
            'books': {
                'test_book1.xlsx': 'book object'
            },
        }
        runner = TestRunner().get_runner(args)
        with _mock_xl_is(row_iter) as mis, self.assertRaises(ValueError):
            runner.run([transform])
        mis.assert_not_called()

    def test_ns(self):
        runner = TestRunner().get_runner()
        self.assertIsInstance(runner.ns, rdflib.namespace.NamespaceManager)

    def test_load_model(self):
        # load_model is a staticmethod on the class
        runner = run.Runner
        with _mock_open('["some", "json"]') as mo:
            data = runner.load_model('test.json')

        self.assertEqual(data, ['some', 'json'])
        mo.assert_called_once_with('test.json', 'rb')

    def test_save_model(self):
        args = {
            'model': {
                'terms': [
                    {'subj': 'a', 'pred': 'b', 'obj': 'c'}
                ]
            }
        }
        runner = TestRunner().get_runner(args)
        with _mock_open('') as mo:
            runner.save_model('test.json')

        mo.assert_called_once_with('test.json', 'w')

        handle = mo()
        # json.dump writes in a way that is awkward to test - 19 separate
        # write calls for the single json term in the model. need to
        # splice them together to get something that's sane
        jsonstring = ''.join([c.args[0] for c in handle.write.mock_calls])
        expected = '{"terms": [{"subj": "a", "pred": "b", "obj": "c"}]}'
        self.assertEqual(jsonstring, expected)
