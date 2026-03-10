"""
Philosophy Classroom Agents
"""

from google.adk.agents import LlmAgent
from google.adk.models import Gemini
from tools.classroom_tools import get_philosophy_rag_tool

# Socrates Agent - The Teacher
# Uses Gemini 3.0 Pro for deep reasoning ("Thinking Mode")
gemini_3_thinking = Gemini(
    model_name="gemini-3-pro-preview",
    parameters={
        "thinking_level": "high", # Enable Thinking Mode
        "temperature": 0.7
    }
)

# Initialize the RAG tool (optional - works without it if corpus not configured)
rag_tool = get_philosophy_rag_tool()
_socrates_tools = [rag_tool] if rag_tool is not None else []

# Adjust instruction based on RAG availability
_socrates_instruction = """
    Ti si Sokrat. Tvoj cilj nije dati odgovor, već voditi učenika do spoznaje.

    Pravila:
    1. Nikada ne odgovaraj direktno na pitanje.
    2. Uvijek odgovaraj protu-pitanjem koje izaziva pretpostavku korisnika.
    3. Koristi analogije iz klasične filozofije i svakodnevnog života.
    4. Ako korisnik tvrdi nešto nelogično, koristi 'reductio ad absurdum'.
    5. Nikada ne izlazi iz lika. Ti si antički filozof.
    6. Budi strpljiv, ali intelektualno rigorozan.
    """
if rag_tool is not None:
    _socrates_instruction += """
    Koristi bazu znanja (PhilosophyKnowledgeBase) da pronađeš relevantne koncepte, ali ih preformuliraj u pitanja.
    """

socrates_agent = LlmAgent(
    name="Socrates",
    model=gemini_3_thinking,
    tools=_socrates_tools,
    instruction=_socrates_instruction
)

# Termination Checker - The Moderator
# Uses Gemini 2.5 Flash for speed
gemini_flash = Gemini(
    model_name="gemini-2.5-flash",
    parameters={
        "temperature": 0.1
    }
)

termination_checker = LlmAgent(
    name="TerminationChecker",
    model=gemini_flash,
    instruction="""
    Analiziraj zadnji odgovor korisnika u kontekstu filozofske debate.
    Tvoj zadatak je odlučiti treba li završiti sesiju.
    
    Vrati 'TERMINATE' ako:
    - Korisnik eksplicitno traži kraj ("kraj", "stop", "dosta", "shvatio sam", "hvala").
    - Korisnik vrijeđa ili je agresivan.
    - Korisnik želi promijeniti temu na nešto ne-filozofsko (npr. "kako da popravim auto").
    
    Vrati 'CONTINUE' ako:
    - Korisnik odgovara na pitanje.
    - Korisnik postavlja novo pitanje.
    - Korisnik traži pojašnjenje.
    
    Samo vrati jednu riječ: TERMINATE ili CONTINUE.
    """
)
