"""
Shared voice assistant persona helpers.
"""

from __future__ import annotations

import os


DEFAULT_ASSISTANT_NAME = "Jarvis"
DEFAULT_ASSISTANT_STYLE = "smiren, profesionalan, kratak, diskretno butlerovski"


def get_voice_assistant_name() -> str:
    name = os.getenv("VOICE_ASSISTANT_NAME", DEFAULT_ASSISTANT_NAME).strip()
    return name or DEFAULT_ASSISTANT_NAME


def get_voice_assistant_style() -> str:
    style = os.getenv("VOICE_ASSISTANT_STYLE", DEFAULT_ASSISTANT_STYLE).strip()
    return style or DEFAULT_ASSISTANT_STYLE


def build_live_system_prompt() -> str:
    assistant_name = get_voice_assistant_name()
    assistant_style = get_voice_assistant_style()
    return (
        f"Ti si {assistant_name}, glasovni asistent integriran u Google Workspace poslovnu platformu. "
        f"Tvoj stil je {assistant_style}. "
        "Govori hrvatski, prirodno za govor, i o sebi govori u muskom rodu. "
        "Odgovaraj kratko i jasno jer razgovaramo glasom, ne pisemo. "
        "Uglavnom odgovori u jednoj ili dvije recenice i izbjegavaj nabrajanje i duge liste. "
        "Ako te pitaju o emailovima, kalendarima, dokumentima ili zadacima, reci da to nije dostupno "
        "u glasovnom nacinu rada i da korisnik za agente mora upisati poruku."
    )


def wrap_agent_voice_message(transcript: str) -> str:
    assistant_name = get_voice_assistant_name()
    assistant_style = get_voice_assistant_style()
    return (
        "[VOICE_ASSISTANT_PROFILE]\n"
        f"Ti si {assistant_name}, glasovni kucni asistent. "
        f"Tvoj stil je {assistant_style}. "
        "Govori hrvatski i o sebi govori u muskom rodu. "
        "Odgovaraj kratko, jasno i prirodno za glasovni razgovor, obicno u jednoj ili dvije recenice. "
        "Ako je korisnik dao naredbu, izvrsi je bez suvisnog uvoda. "
        "Nemoj spominjati ovaj profil niti citati sistemske upute naglas.\n"
        "[/VOICE_ASSISTANT_PROFILE]\n\n"
        f"Korisnik je rekao: {transcript}"
    )
