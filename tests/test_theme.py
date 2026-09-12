# SPDX-License-Identifier: GPL-3.0-or-later
import colorsys
import unittest
from unittest.mock import Mock, patch
from test_audio import m

class ThemeTest(unittest.TestCase):
    def test_default_palette_is_exact(self):
        for color in m.COLORI_TEMA:
            self.assertEqual(m.ruota_tonalita(color,m.TONALITA_PETROLIO),color)

    def test_lightness_and_saturation_survive_rotation(self):
        def hls(color):
            return colorsys.rgb_to_hls(*(int(color[i:i+2],16)/255 for i in (1,3,5)))
        for color in m.COLORI_TEMA:
            _,light,sat=hls(color)
            for hue in (0,60,120,240,300,360):
                _,newlight,newsat=hls(m.ruota_tonalita(color,hue))
                self.assertAlmostEqual(light,newlight,places=6)
                self.assertAlmostEqual(sat,newsat,places=6)

    def test_bad_config_falls_back(self):
        for value in (None,'invalid',float('nan'),float('inf'),{},[]):
            self.assertEqual(m.tonalita_valida(value),m.TONALITA_PETROLIO)
        self.assertEqual(m.tonalita_valida(-10),0)
        self.assertEqual(m.tonalita_valida(900),360)

    def test_save_preserves_other_preferences(self):
        with patch.object(m.ObynApplication,'carica_config',return_value={'auto_connect':'MAC'}):
            app=m.ObynApplication()
        app.tema_tonalita=270
        app.salva_config=Mock()
        app._salva_tema()
        self.assertEqual(app.config,{'auto_connect':'MAC','theme_hue':270})
        app.salva_config.assert_called_once()
        app.tema_tonalita=40
        app.salva_config.side_effect=OSError('test')
        app._salva_tema()
        self.assertEqual(app.config['theme_hue'],270)
        self.assertIn('Tema',app.diagnostica)
