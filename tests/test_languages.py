# SPDX-License-Identifier: GPL-3.0-or-later
import gettext
from pathlib import Path
import unittest
from test_audio import m

class LanguageTests(unittest.TestCase):
    def manager(self, preference='auto', environ=None):
        return m.LanguageManager('obyn', [Path(__file__).resolve().parents[1]/'locale'],
                                 preference=preference, environ=environ or {})

    def test_locale_precedence_and_fallback(self):
        cases = [({},'en'), ({'LANG':'it_IT.UTF-8'},'it'),
                 ({'LANG':'it_IT','LC_ALL':'en_US.UTF-8'},'en'),
                 ({'LANG':'it_IT','LC_MESSAGES':'en_GB'},'en'),
                 ({'LANG':'de_DE'},'en'), ({'LANG':'en_US','LANGUAGE':'de:it'},'it'),
                 ({'LC_ALL':'C','LANGUAGE':'it'},'en')]
        for env, expected in cases:
            self.assertEqual(self.manager(environ=env).language, expected)
        self.assertEqual(self.manager('it', {'LC_ALL':'en_US'}).language,'it')

    def test_catalog_and_plural(self):
        lang=self.manager('en')
        self.assertTrue(lang.catalog_loaded)
        self.assertEqual(lang.gettext('Connesso'),'Connected')
        self.assertEqual(lang.ngettext('{count} dispositivo osservato.', '{count} dispositivi osservati.', 1).format(count=1),'1 device observed.')
        self.assertEqual(lang.ngettext('{count} dispositivo osservato.', '{count} dispositivi osservati.', 0).format(count=0),'0 devices observed.')
        lang.configure('it')
        self.assertEqual(lang.gettext('Connesso'),'Connesso')

    def test_unknown_text_and_missing_catalog(self):
        lang=self.manager('en')
        raw='org.bluez.Error.Failed AA:BB:CC:DD:EE:FF'
        self.assertEqual(lang.gettext(raw),raw)
        missing=m.LanguageManager('missing',[],preference='en')
        self.assertFalse(missing.catalog_loaded)
        self.assertEqual(missing.gettext('Connesso'),'Connesso')

    def test_all_marked_messages_have_english(self):
        import ast
        tree=ast.parse((Path(__file__).resolve().parents[1]/'src/obyn.py').read_text())
        lang=self.manager('en')
        for n in ast.walk(tree):
            if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='tr' and n.args and isinstance(n.args[0],ast.Constant):
                key=n.args[0].value
                self.assertIn(key,lang.translation._catalog,key)
