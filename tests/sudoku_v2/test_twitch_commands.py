from django.test import SimpleTestCase
from sudoku_v2.twitch.commands import parse_command, normalize_channel


class TwitchCommandTests(SimpleTestCase):
    def test_parser_defaults_aliases_quotes_and_raw_args(self):
        cases=[('!rotate',('ROLL','*',{})),('!roll',('ROLL','*',{})),
               ('!shadow * 3',('SHADOW_BOX','*',{'box':2})),
               ('!blur "Игрок 2" 3',('SHADOW_BOX','Игрок 2',{'box':2})),
               ("!blur O'Brien 3",('SHADOW_BOX',"O'Brien",{'box':2})),
               (r'!blur A\B 3',('SHADOW_BOX',r'A\B',{'box':2})),
               (r'!blur "A\B C" 3',('SHADOW_BOX',r'A\B C',{'box':2})),
               ('!swap * col 1 9',('SWAP','*',{'axis':'col','first':0,'second':8})),
               ('!blur "сломано',('SHADOW_BOX','*',{})),
               ('!dance * нет',('DANCE','*',{})),
               ('!dance * 1 99999',('DANCE','*',{'box':0}))]
        for text,expected in cases:
            with self.subTest(text=text):
                command=parse_command(text)
                self.assertEqual((command.kind,command.name,command.raw_params),expected)
        for text in ['hi','!unknown *','!','!blurred * 1','!gray','!grey','!pulse * 1']:
            self.assertIsNone(parse_command(text))

    def test_channel_login_only(self):
        self.assertEqual(normalize_channel('  Some_Channel '),'some_channel')
        for value in ['https://twitch.tv/name','#name','bad name','x'*26,True,None,'']:
            with self.subTest(value=value),self.assertRaises(ValueError):normalize_channel(value)
