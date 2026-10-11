import re
import shlex
from .types import ParsedBonusCommand

COMMANDS={'swap':'SWAP','blur':'SHADOW_BOX','shadow':'SHADOW_BOX','rotate':'ROLL',
          'roll':'ROLL','dance':'DANCE','gray':'GRAYSCALE','pulse':'PULSE'}


def normalize_channel(channel):
    if not isinstance(channel,str) or not re.fullmatch(r'[a-zA-Z0-9_]{1,25}',channel.strip()):
        raise ValueError('Use a Twitch login without a URL')
    return channel.strip().lower()


def parse_command(text: str) -> ParsedBonusCommand | None:
    if not isinstance(text,str) or not text.startswith('!'):
        return None
    kind=COMMANDS.get(text.split(maxsplit=1)[0][1:].lower())
    if not kind:return None
    lexer=shlex.shlex(text,posix=True)
    lexer.whitespace_split=True;lexer.commenters='';lexer.quotes='"';lexer.escape=''
    try:parts=list(lexer)
    except ValueError:return ParsedBonusCommand(kind,'*',{})
    name=parts[1] if len(parts)>1 else '*'
    args=parts[2:];params={}
    def coordinate(value):
        if not re.fullmatch(r'[0-9]{1,3}',value):return None
        return int(value)-1
    if kind=='SWAP':
        if args:params['axis']=args[0].lower()
        for key,value in zip(('first','second'),args[1:3]):
            number=coordinate(value)
            if number is not None:params[key]=number
    elif args:
        number=coordinate(args[0])
        if number is not None:params['box']=number
    return ParsedBonusCommand(kind,name,params)
