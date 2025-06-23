# ===== apps/documents/services/metadata_extraction.py =====
import re
import os
import mimetypes
import logging
from datetime import datetime, date
from typing import Dict, List, Optional, Tuple
from pathlib import Path

# Imports pour traitement de fichiers
import PyPDF2
import docx
import unicodedata
from bs4 import BeautifulSoup
import chardet
import langdetect
from langdetect import detect, DetectorFactory

# Imports Django
from django.utils import timezone
from django.core.files.storage import default_storage

from ..models import Document, DocumentSource, DocumentExtractionLog

# Configuration pour une détection de langue reproductible
DetectorFactory.seed = 0

logger = logging.getLogger(__name__)


class MetadataExtractionService:
    """Service d'extraction automatique de métadonnées à partir de documents"""

    # Patterns de reconnaissance améliorés pour différentes métadonnées
    TITLE_PATTERNS = [
        # Pattern spécifique EMA
        r'^(European Medicines Agency\s.+?)(?:\n|\r|$)',

        # Pattern général pour titres réglementaires (guidance, advice, etc.)
        r'^[A-Z][^\n]{30,150}(?:procedure|guidance|advice|guideline|directive|regulation|recommendation)[^\n]*(?:\n|\r|$)',

        # Nouveau pattern général efficace pour titres substantiels
        r'^(?:On-boarding|Introduction|Guidance|Procedure|Regulation|Directive|Advice|Guideline)\b.+?(?:\n|\r|$)',

        # Patterns explicites avec mots-clés existants
        r'(?:title|titre|título|titel|titolo|název)\s*:?\s*(.+?)(?:\n|\r|$)',
        r'(?:subject|sujet|objet|oggetto|asunto|onderwerp)\s*:?\s*(.+?)(?:\n|\r|$)',

        # Patterns existants pour documents réglementaires pharma
        r'(?:guideline|guidance|guide|lignes directrices|leitfaden|guía)\s+(?:on|sur|für|para|su)\s+(.+?)(?:\n|\r|$)',
        r'(?:procedure|procédure|procedimiento|procedura|verfahren)\s+(?:for|pour|für|para|per)\s+(.+?)(?:\n|\r|$)',

        r'(?:regulation|règlement|reglamento|regolamento|verordnung)\s+(?:no|n°|nr)\s*\.?\s*\d+[/\-]\d+\s*(?:on|sur|über|sobre|su)\s+(.+?)(?:\n|\r|$)',
        r'(?:directive|direction|directiva|direttiva|richtlinie)\s+\d+[/\-]\d+[/\-]?\w*\s*(?:on|sur|über|sobre|su)\s+(.+?)(?:\n|\r|$)',

        # Patterns ICH/EMA/FDA spécifiques
        r'(?:ICH|EMA|FDA|ANSM|MHRA)\s+(?:guideline|guidance|guide)\s*[:\-]?\s*(.+?)(?:\n|\r|$)',
        r'(?:ICH\s+[QEM]\d{1,2}[A-Z]?)\s*[:\-]?\s*(.+?)(?:\n|\r|$)',
        r'(?:EMA/\d+/\d+(?:/\d+)?)\s*[:\-]?\s*(.+?)(?:\n|\r|$)',

        # Patterns pour documents administratifs
        r'(?:circular|circulaire|circolare|circular)\s+(?:no|n°|nr)\s*\.?\s*\d+\s*[:\-]?\s*(.+?)(?:\n|\r|$)',
        r'(?:notice|notification|avis|aviso|notifica)\s+(?:to|aux|an|a|al)\s+(.+?)(?:\n|\r|$)',
        r'(?:memorandum|mémorandum|memorándum)\s+(?:on|sur|sobre|su)\s+(.+?)(?:\n|\r|$)',

        # Patterns basés sur la structure
        r'^([A-Z][A-Z0-9\s\-–—]{10,150})$',  # Ligne en majuscules avec ponctuation
        r'^([A-Z][^.\n]{15,150})\s*$',  # Première ligne substantielle
        r'^(?:\d+\.?\s*)?([A-Z][^.\n]{15,150})(?:\n|\r|$)',  # Avec numérotation optionnelle
        r'^\s*(?:I+\.?\s*)?([A-Z][^.\n]{15,150})\s*$',  # Avec numérotation romaine

        # Patterns multilingues étendus
        r'^(?:1\.?\s*)?(?:introduction|einleitung|introducción|introduzione|inleiding)\s*[:\-]?\s*(.+?)(?:\n|\r|$)',
        r'(?:re|objet|betreff|oggetto|asunto|betreft)\s*:?\s*(.+?)(?:\n|\r|$)',

        # Fallback patterns
        r'^(.{15,150})(?:\n|\r)',  # Première ligne non vide
    ]

    DATE_PATTERNS = [
        # Patterns avec contexte explicite (en premier)
        r'(?:date|dated|datum|fecha|data)\s*:?\s*(\d{1,2}[-/\.]\d{1,2}[-/\.]\d{2,4})',
        r'(?:publié|published|veröffentlicht|pubblicato|publicado)\s+(?:le|on|am|il|el)?\s*:?\s*(\d{1,2}[-/\.]\d{1,2}[-/\.]\d{2,4})',
        r'(?:effective|efficace|wirksam|efectivo)\s+(?:date|le|am|dal|desde)?\s*:?\s*(\d{1,2}[-/\.]\d{1,2}[-/\.]\d{2,4})',
        r'(?:version|révision|revision|revisione|revisión)\s+(?:du|of|vom|del|van)?\s*:?\s*(\d{1,2}[-/\.]\d{1,2}[-/\.]\d{2,4})',
        r'(?:issued|émis|ausgestellt|emesso|emitido)\s+(?:on|le|am|il|el)?\s*:?\s*(\d{1,2}[-/\.]\d{1,2}[-/\.]\d{2,4})',
        r'(?:approved|approuvé|genehmigt|approvato|aprobado)\s+(?:on|le|am|il|el)?\s*:?\s*(\d{1,2}[-/\.]\d{1,2}[-/\.]\d{2,4})',
        r'(?:validated|validé|validiert|validato|validado)\s+(?:on|le|am|il|el)?\s*:?\s*(\d{1,2}[-/\.]\d{1,2}[-/\.]\d{2,4})',

        # Formats ISO et standards exacts
        r'\b(\d{4}-\d{2}-\d{2})\b',  # 2024-03-15
        r'\b(\d{4}/\d{2}/\d{2})\b',  # 2024/03/15
        r'\b(\d{4}\.\d{2}\.\d{2})\b',  # 2024.03.15
        r'\b(\d{4}_\d{2}_\d{2})\b',  # 2024_03_15

        # Formats européens exacts
        r'\b(\d{1,2}/\d{1,2}/\d{4})\b',  # 15/03/2024 ou 5/3/2024
        r'\b(\d{1,2}-\d{1,2}-\d{4})\b',  # 15-03-2024
        r'\b(\d{1,2}\.\d{1,2}\.\d{4})\b',  # 15.03.2024
        r'\b(\d{1,2}\s+\d{1,2}\s+\d{4})\b',  # 15 03 2024

        # Formats américains
        r'\b(\d{1,2}/\d{1,2}/\d{2,4})\b',  # MM/DD/YY ou MM/DD/YYYY
        r'\b(\d{1,2}-\d{1,2}-\d{2,4})\b',  # MM-DD-YY ou MM-DD-YYYY

        # Formats avec mois textuels complets
        r'\b(\d{1,2})\s+'
        r'(January|February|March|April|May|June|July|August|September|October|November|December|'
        r'Janvier|Février|Mars|Avril|Mai|Juin|Juillet|Août|Septembre|Octobre|Novembre|Décembre|'
        r'Enero|Febrero|Marzo|Abril|Mayo|Junio|Julio|Agosto|Septiembre|Octubre|Noviembre|Diciembre|'
        r'Gennaio|Febbraio|Marzo|Aprile|Maggio|Giugno|Luglio|Agosto|Settembre|Ottobre|Novembre|Dicembre|'
        r'Januar|Februar|März|April|Mai|Juni|Juli|August|September|Oktober|November|Dezember|'
        r'Januari|Februari|Maart|April|Mei|Juni|Juli|Augustus|September|Oktober|November|December)\s+'
        r'(\d{4})\b',

        # Formats avec mois abrégés
        r'\b(\d{1,2})[\s\-\.]+'
        r'(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|'
        r'janv|févr|mars|avr|mai|juin|juil|août|sept|oct|nov|déc|'
        r'ene|feb|mar|abr|may|jun|jul|ago|sep|oct|nov|dic|'
        r'gen|feb|mar|apr|mag|giu|lug|ago|set|ott|nov|dic)'
        r'\.?[\s\-\.]+(\d{4})\b',

        # Formats inversés (année en premier)
        r'\b(\d{4})[\s\-\./]+(\d{1,2})[\s\-\./]+(\d{1,2})\b',

        # Année seule
        r'\b(20[0-3]\d)\b',  # 2000-2039
        r'\b(19[89]\d)\b',  # 1980-1999
    ]


    VERSION_PATTERNS = [
        # Patterns explicites avec mots-clés
        r'(?:version|ver\.?|v\.?|vers\.?)\s*:?\s*(\d+(?:\.\d+)*(?:[a-zA-Z]+\d*)?)',
        r'(?:révision|revision|rev\.?|rév\.?)\s*:?\s*(\d+(?:\.\d+)*(?:[a-zA-Z]+\d*)?)',
        r'(?:release|rel\.?|édition|edition|ed\.?)\s*:?\s*(\d+(?:\.\d+)*(?:[a-zA-Z]+\d*)?)',
        r'(?:draft|ébauche|brouillon|entwurf|bozza|borrador)\s*:?\s*(\d+(?:\.\d+)*(?:[a-zA-Z]+\d*)?)',

        # Patterns avec préfixes spécifiques
        r'\bv(\d+(?:\.\d+)*(?:[a-zA-Z]+\d*)?)\b',
        r'\br(\d+(?:\.\d+)*)\b',  # r1.2.3
        r'(?:issue|émission|ausgabe|emissione|emisión)\s*:?\s*(\d+(?:\.\d+)*)',

        # Patterns pour documents réglementaires
        r'(?:amendment|amendement|änderung|emendamento|enmienda)\s*:?\s*(\d+)',
        r'(?:update|mise à jour|aktualisierung|aggiornamento|actualización)\s*:?\s*(\d+(?:\.\d+)*)',
        r'(?:corrigendum|correctif|korrigendum|errata)\s*:?\s*(\d+)',

        # Patterns avec dates
        r'(?:version|v\.?)\s+(?:du|of|vom|del|van)?\s*\d{1,2}[-/\.]\d{1,2}[-/\.]\d{2,4}\s*[:\-]?\s*(\d+(?:\.\d+)*)',

        # Patterns alphanumériques
        r'(?:version|v\.?)\s*:?\s*([A-Z]\d+(?:\.\d+)*)',  # A1.2
        r'(?:version|v\.?)\s*:?\s*(\d+[a-zA-Z])',  # 1a, 2b

        # Patterns spéciaux
        r'(?:final|finale|endgültig|definitivo)\s+(?:version|v\.?)?\s*:?\s*(\d+(?:\.\d+)*)',
        r'(?:working|travail|arbeit|lavoro|trabajo)\s+(?:version|v\.?)?\s*:?\s*(\d+(?:\.\d+)*)',
    ]

    LANGUAGE_MAPPING = {
        'bg': 'Bulgarian',
        'es': 'Spanish',
        'cs': 'Czech',
        'da': 'Danish',
        'de': 'German',
        'et': 'Estonian',
        'el': 'Greek',
        'en': 'English',
        'fr': 'French',
        'ga': 'Irish',
        'hr': 'Croatian',
        'it': 'Italian',
        'lv': 'Latvian',
        'lt': 'Lithuanian',
        'hu': 'Hungarian',
        'mt': 'Maltese',
        'nl': 'Dutch',
        'pl': 'Polish',
        'pt': 'Portuguese',
        'ro': 'Romanian',
        'sk': 'Slovak',
        'sl': 'Slovenian',
        'fi': 'Finnish',
        'sv': 'Swedish',
        'no': 'Norwegian',
        'is': 'Icelandic',
        'tr': 'Turkish',
        'ru': 'Russian',
        'uk': 'Ukrainian',
        'ja': 'Japanese',
        'ko': 'Korean',
        'zh': 'Chinese',
        'ar': 'Arabic',
        'he': 'Hebrew',
    }

    # Langues européennes (codes ISO)
    EUROPEAN_LANGUAGES = {
        'bg', 'cs', 'da', 'de', 'et', 'el', 'fr', 'ga', 'hr', 'it',
        'lv', 'lt', 'hu', 'mt', 'nl', 'pl', 'ro', 'sk', 'sl', 'fi',
        'sv', 'no', 'is'
    }

    SOURCE_PATTERNS = {
        'EMA': [
            # Patterns généraux EMA
            r'\b(?:european medicines agency|ema|emea)\b',
            r'\bema\.europa\.eu\b',
            r'\bemea\.europa\.eu\b',

            # Références documentaires EMA
            r'EMA/\d{3,6}/\d{4}(?:/Rev\.\d+)?',  # EMA/123456/2024/Rev.1
            r'EMA/[A-Z]+/\d+/\d{4}',  # EMA/CHMP/123/2024
            r'EMEA/H/C/\d{6}',  # Centralized procedure numbers
            r'EU/\d{1}/\d{2}/\d{3,4}',  # EU procedure numbers

            # Comités et groupes de travail
            r'\b(?:CHMP|CVMP|COMP|HMPC|CAT|PRAC|PDCO)\b',
            r'(?:CHMP|CVMP)/(?:ICH|QWP|BWP|SWP|EWP|SAWP|VWP|IWP|ORGAM|PhVWP)',
            r'Committee for (?:Medicinal Products|Human Use|Veterinary|Orphan)',

            # Types de documents EMA
            r'(?:Scientific|Regulatory|Procedural)\s+(?:Guideline|Guidance)',
            r'(?:Reflection|Position|Concept)\s+Paper',
            r'European Public Assessment Report',
            r'\bEPAR\b',
            r'(?:Draft|Final)\s+(?:Guideline|Guidance|Opinion)',
        ],

        'FDA': [
            # Patterns généraux FDA
            r'\b(?:food and drug administration|fda|usfda)\b',
            r'\bfda\.gov\b',
            r'U\.?S\.?\s+FDA',

            # Centres FDA
            r'\b(?:CDER|CBER|CDRH|CFSAN|CVM|NCTR|ORA)\b',
            r'Center for (?:Drug Evaluation|Biologics|Devices|Food Safety)',

            # Types de documents FDA
            r'FDA\s+(?:Guidance|Draft Guidance|Final Guidance)',
            r'(?:Industry|Investigator|Clinical)\s+Guidance',
            r'(?:NDA|ANDA|BLA|IND|IDE|PMA|510\(k\))\s+(?:Application|Submission)',
            r'FDA-2\d{3}-[DNG]-\d{4}',  # Docket numbers
            r'FDA\s+Form\s+\d{4}',

            # Regulatory pathways
            r'(?:505\(b\)|505\(j\)|351\(a\)|351\(k\))',
            r'(?:Fast Track|Breakthrough Therapy|Priority Review|Accelerated Approval)',
        ],

        'ANSM': [
            # Patterns généraux ANSM
            r'\b(?:ansm|afssaps|agence nationale de sécurité du médicament)\b',
            r'\bansm\.sante\.fr\b',
            r'Agence française de sécurité sanitaire',

            # Références documentaires
            r'ANSM-\d{4}-\d{2}-\d{2}',
            r'(?:RCP|SMR|ASMR|AMM)',  # French specific terms

            # Types de documents ANSM
            r'(?:Recommandation|Avis|Décision|Rapport)\s+(?:ANSM|Agence)',
            r'(?:Bonnes Pratiques|Référentiel|Guide)',
            r'(?:Autorisation|Mise sur le marché|Pharmacovigilance)',
        ],

        'MHRA': [
            # Patterns généraux MHRA
            r'\b(?:mhra|medicines and healthcare products regulatory agency)\b',
            r'\bmhra\.gov\.uk\b',
            r'UK\s+(?:MHRA|Medicines)',

            # Systèmes et programmes MHRA
            r'(?:Yellow Card|Blue Guide|Orange Guide)',
            r'(?:UKPAR|Public Assessment Report)',
            r'(?:GMP|GCP|GLP|GMDP)\s+(?:Inspection|Certificate)',

            # Références documentaires
            r'MHRA/\d{4}/\d+',
            r'(?:MA|MIA|WDA)\(\w+\)\d+',  # License numbers
        ],

        'ICH': [
            # Patterns généraux ICH
            r'\b(?:ich|international council for harmonisation)\b',
            r'\bich\.org\b',
            r'International Conference on Harmonisation',

            # Guidelines ICH
            r'ICH\s+[QESM]\d{1,2}(?:\([A-Z]\))?(?:\s+R\d+)?',  # ICH Q1A(R2)
            r'ICH\s+(?:Quality|Safety|Efficacy|Multidisciplinary)\s+Guidelines?',
            r'(?:Step|Etape)\s+[1-5]\s+(?:Document|Version)',

            # Topics ICH
            r'(?:CTD|eCTD|MedDRA|E2B|M4Q|S9)',
            r'Common Technical Document',
        ],

        'WHO': [
            # Patterns généraux WHO
            r'\b(?:world health organization|who|oms)\b',
            r'\bwho\.int\b',
            r'Organisation mondiale de la santé',

            # Documents WHO
            r'WHO\s+(?:Technical Report Series|TRS)\s+\d+',
            r'WHO\s+Expert Committee',
            r'(?:International|World)\s+Pharmacopoeia',
            r'WHO\s+(?:Guideline|Standard|Recommendation)',
            r'(?:GMP|GDP|GCP)\s+for\s+pharmaceutical',

            # Programmes WHO
            r'(?:Prequalification|PQ)\s+(?:Programme|Team)',
            r'Essential Medicines List',
        ],

        'EDQM': [
            # Patterns généraux EDQM
            r'\b(?:edqm|european directorate for the quality of medicines)\b',
            r'\bedqm\.eu\b',
            r'Council of Europe',

            # Pharmacopée européenne
            r'(?:European|Ph\.\s*Eur\.|Pharmacopoeia Europaea)',
            r'(?:EP|Ph\.\s*Eur\.)\s+\d+\.\d+',  # EP 10.0
            r'(?:Monograph|General Chapter)\s+\d+',

            # Certificats et documents
            r'(?:CEP|Certificate of Suitability)',
            r'(?:TSE|Transmissible Spongiform)',
            r'EDQM\s+(?:Guideline|Procedure|Policy)',
        ],

        # Ajout d'autres agences importantes
        'Health Canada': [
            r'\b(?:health canada|santé canada)\b',
            r'\bhc-sc\.gc\.ca\b',
            r'(?:TPD|BGTD|MHPD|NHPD)',  # Directorates
            r'(?:NOC|DIN|NPN)\s+\d+',  # Canadian identifiers
            r'Canadian\s+(?:Guideline|Guidance|Standard)',
        ],

        'TGA': [
            r'\b(?:tga|therapeutic goods administration)\b',
            r'\btga\.gov\.au\b',
            r'Australian\s+(?:Register|Regulatory|Guidelines)',
            r'(?:ARTG|AUST)\s+[RL]\s+\d+',  # Australian identifiers
        ],

        'PMDA': [
            r'\b(?:pmda|pharmaceuticals and medical devices agency)\b',
            r'\bpmda\.go\.jp\b',
            r'(?:Japanese|Japan)\s+(?:Regulatory|Guidelines)',
            r'(?:MHLW|Ministry of Health)',
        ],

        'SwissMedic': [
            r'\bswissmedic\b',
            r'\bswissmedic\.ch\b',
            r'(?:Swiss|Suisse|Schweiz)\s+(?:Agency|Regulatory)',
            r'(?:Autorisation|Zulassung)\s+\d+',
        ],
    }

    COUNTRY_PATTERNS = {
        # Union Européenne et variantes
        'EU': [
            r'\b(?:european union|eu|union européenne|ue|europäische union|unione europea|unión europea|eu-wide|eu wide|europe-wide)\b',
            r'\b(?:eea|european economic area|espace économique européen)\b',
            r'\b(?:member states|états membres|mitgliedstaaten|stati membri|estados miembros)\b',
            r'\b(?:european|européen|europäisch|europeo|europeu)\s+(?:regulation|directive|law|legislation)\b',
            r'\b(?:brussels|bruxelles|european commission|commission européenne)\b',
        ],

        # Pays européens majeurs
        'France': [
            r'\b(?:france|french|français|française|république française|hexagone)\b',
            r'\b(?:paris|lyon|marseille|toulouse|nice|nantes|strasbourg|montpellier|bordeaux|lille)\b',
            r'\b(?:afssaps|ansm|has|anses|ministère de la santé)\b',
            r'\b(?:fr|\.fr|france métropolitaine|dom-tom)\b',
        ],

        'Germany': [
            r'\b(?:germany|deutschland|german|deutsch|deutsche|bundesrepublik|allemagne|germania)\b',
            r'\b(?:berlin|munich|münchen|hamburg|cologne|köln|frankfurt|stuttgart|düsseldorf|dortmund|essen)\b',
            r'\b(?:bfarm|pei|dimdi|g-ba|bundesministerium für gesundheit)\b',
            r'\b(?:de|\.de|baden-württemberg|bayern|nordrhein-westfalen)\b',
        ],

        'UK': [
            r'\b(?:united kingdom|uk|great britain|grande-bretagne|großbritannien|gran bretagna|reino unido)\b',
            r'\b(?:england|scotland|wales|northern ireland|british|britannique|britisch|britannico|británico)\b',
            r'\b(?:london|manchester|birmingham|glasgow|liverpool|edinburgh|bristol|leeds|sheffield|newcastle)\b',
            r'\b(?:mhra|nice|nhs|gmc|department of health)\b',
            r'\b(?:gb|\.uk|england and wales)\b',
        ],

        'Italy': [
            r'\b(?:italy|italia|italian|italiano|italiana|italien|italie)\b',
            r'\b(?:rome|roma|milan|milano|naples|napoli|turin|torino|palermo|genoa|genova|bologna|florence|firenze)\b',
            r'\b(?:aifa|ministero della salute|istituto superiore di sanità)\b',
            r'\b(?:it|\.it|repubblica italiana)\b',
        ],

        'Spain': [
            r'\b(?:spain|españa|spanish|español|española|espagne|spanien|spagna)\b',
            r'\b(?:madrid|barcelona|valencia|seville|sevilla|zaragoza|málaga|murcia|palma|bilbao)\b',
            r'\b(?:aemps|ministerio de sanidad|agencia española)\b',
            r'\b(?:es|\.es|reino de españa|comunidades autónomas)\b',
        ],

        'Netherlands': [
            r'\b(?:netherlands|nederland|dutch|nederlands|nederlandse|pays-bas|niederlande|paesi bassi|países bajos)\b',
            r'\b(?:amsterdam|rotterdam|the hague|den haag|utrecht|eindhoven|tilburg|groningen|almere|breda|nijmegen)\b',
            r'\b(?:cbg-meb|igj|rivm|ministerie van vws)\b',
            r'\b(?:nl|\.nl|holland|koninkrijk der nederlanden)\b',
        ],

        'Belgium': [
            r'\b(?:belgium|belgië|belgique|belgian|belge|belgisch|belgische|belgio|bélgica)\b',
            r'\b(?:brussels|bruxelles|antwerp|antwerpen|anvers|ghent|gent|gand|charleroi|liège|luik|bruges|brugge)\b',
            r'\b(?:famhp|afmps|fagg|sciensano|inami|riziv)\b',
            r'\b(?:be|\.be|royaume de belgique|koninkrijk belgië)\b',
        ],

        'Switzerland': [
            r'\b(?:switzerland|suisse|schweiz|svizzera|suiza|swiss|suisse|schweizerisch|svizzero|suizo)\b',
            r'\b(?:zurich|zürich|geneva|genève|genf|ginevra|basel|bâle|lausanne|bern|berne|winterthur|lucerne)\b',
            r'\b(?:swissmedic|bag|ofsp|swiss agency)\b',
            r'\b(?:ch|\.ch|confédération suisse|schweizerische eidgenossenschaft)\b',
        ],

        'Austria': [
            r'\b(?:austria|österreich|austrian|österreichisch|austriaco|autriche|autrichien)\b',
            r'\b(?:vienna|wien|graz|linz|salzburg|innsbruck|klagenfurt|villach|wels|sankt pölten)\b',
            r'\b(?:ages|basg|österreichische agentur)\b',
            r'\b(?:at|\.at|republik österreich)\b',
        ],

        # Pays nordiques
        'Sweden': [
            r'\b(?:sweden|sverige|swedish|svensk|svenska|suède|schweden|svezia|suecia)\b',
            r'\b(?:stockholm|gothenburg|göteborg|malmö|uppsala|västerås|örebro|linköping|helsingborg)\b',
            r'\b(?:läkemedelsverket|lakemedelsverket|medical products agency)\b',
            r'\b(?:se|\.se|konungariket sverige)\b',
        ],

        'Denmark': [
            r'\b(?:denmark|danmark|danish|dansk|danske|danemark|dänemark|danimarca|dinamarca)\b',
            r'\b(?:copenhagen|københavn|aarhus|odense|aalborg|esbjerg|randers|kolding|horsens|vejle)\b',
            r'\b(?:dkma|lægemiddelstyrelsen|danish medicines agency)\b',
            r'\b(?:dk|\.dk|kongeriget danmark)\b',
        ],

        'Norway': [
            r'\b(?:norway|norge|norwegian|norsk|norske|norvège|norwegen|norvegia|noruega)\b',
            r'\b(?:oslo|bergen|trondheim|stavanger|drammen|fredrikstad|kristiansand|sandnes|tromsø|sarpsborg)\b',
            r'\b(?:noma|statens legemiddelverk|norwegian medicines agency)\b',
            r'\b(?:no|\.no|kongeriket norge)\b',
        ],

        'Finland': [
            r'\b(?:finland|suomi|finnish|suomalainen|finlande|finnland|finlandia)\b',
            r'\b(?:helsinki|espoo|tampere|vantaa|oulu|turku|jyväskylä|lahti|kuopio|kouvola)\b',
            r'\b(?:fimea|lääkealan turvallisuus)\b',
            r'\b(?:fi|\.fi|suomen tasavalta)\b',
        ],

        # Europe de l'Est
        'Poland': [
            r'\b(?:poland|polska|polish|polski|polskie|pologne|polen|polonia)\b',
            r'\b(?:warsaw|warszawa|kraków|krakow|łódź|lodz|wrocław|wroclaw|poznań|poznan|gdańsk|gdansk)\b',
            r'\b(?:urpl|główny inspektorat|office for registration)\b',
            r'\b(?:pl|\.pl|rzeczpospolita polska)\b',
        ],

        # Pays hors Europe
        'USA': [
            r'\b(?:usa|united states|america|american|états-unis|etats-unis|vereinigte staaten|stati uniti|estados unidos)\b',
            r'\b(?:washington|new york|los angeles|chicago|houston|philadelphia|phoenix|san antonio|san diego|dallas)\b',
            r'\b(?:fda|cdc|nih|cms|hhs|usp)\b',
            r'\b(?:us|\.us|\.gov|united states of america)\b',
        ],

        'Canada': [
            r'\b(?:canada|canadian|canadien|canadienne|kanada|kanadisch)\b',
            r'\b(?:ottawa|toronto|montreal|montréal|vancouver|calgary|edmonton|québec|quebec|winnipeg|hamilton)\b',
            r'\b(?:health canada|santé canada|hc-sc|tpd|hpfb)\b',
            r'\b(?:ca|\.ca|gouvernement du canada)\b',
        ],

        'Australia': [
            r'\b(?:australia|australian|australie|australien|australiano)\b',
            r'\b(?:sydney|melbourne|brisbane|perth|adelaide|gold coast|newcastle|canberra|sunshine coast)\b',
            r'\b(?:tga|therapeutic goods administration|department of health)\b',
            r'\b(?:au|\.au|commonwealth of australia)\b',
        ],

        'Japan': [
            r'\b(?:japan|japanese|japon|japonais|giappone|giapponese|japón|japonés)\b',
            r'\b(?:tokyo|osaka|yokohama|nagoya|sapporo|kobe|kyoto|fukuoka|kawasaki|saitama)\b',
            r'\b(?:pmda|mhlw|ministry of health|pharmaceuticals and medical devices agency)\b',
            r'\b(?:jp|\.jp|nippon|nihon)\b',
        ],
    }

    DOCUMENT_TYPE_PATTERNS = {
        'guideline': [
            # Anglais
            r'\b(?:guideline|guidance|guide|guiding principles|best practices)\b',
            # Français
            r'\b(?:ligne directrice|lignes directrices|guide|recommandation|bonnes pratiques)\b',
            # Allemand
            r'\b(?:leitlinie|leitfaden|richtlinie|anleitung|empfehlung)\b',
            # Italien
            r'\b(?:linea guida|linee guida|guida|raccomandazione)\b',
            # Espagnol
            r'\b(?:directriz|directrices|guía|recomendación|buenas prácticas)\b',
            # Néerlandais
            r'\b(?:richtlijn|richtsnoer|leidraad|aanbeveling)\b',
        ],

        'procedure': [
            # Multilingue
            r'\b(?:procedure|process|protocol|method|methodology)\b',
            r'\b(?:procédure|processus|protocole|méthode|méthodologie)\b',
            r'\b(?:verfahren|prozess|protokoll|methode|methodologie)\b',
            r'\b(?:procedura|processo|protocollo|metodo|metodologia)\b',
            r'\b(?:procedimiento|proceso|protocolo|método|metodología)\b',
            # Termes spécifiques
            r'\b(?:sop|standard operating procedure|work instruction)\b',
            r'\b(?:mode opératoire|instruction de travail)\b',
        ],

        'regulation': [
            # Multilingue
            r'\b(?:regulation|regulatory|règlement|réglementaire|reglamento|regulación)\b',
            r'\b(?:verordnung|regulierung|regolamento|regolamentazione)\b',
            r'\b(?:directive|direction|direktive|direttiva|directiva)\b',
            r'\b(?:law|legislation|act|statute|decree)\b',
            r'\b(?:loi|législation|décret|arrêté)\b',
            r'\b(?:gesetz|rechtsvorschrift|dekret)\b',
            # Références réglementaires
            r'(?:EC|CE|EG)\s*(?:No|Nr|N°)?\s*\d+/\d+',
            r'(?:EU|UE)\s*(?:No|Nr|N°)?\s*\d+/\d+',
        ],

        'variation': [
            # Termes pharmaceutiques
            r'\b(?:variation|amendment|modification|change|update)\b',
            r'\b(?:variation|amendement|modification|changement|mise à jour)\b',
            r'\b(?:änderung|ergänzung|modifikation|aktualisierung)\b',
            r'\b(?:variazione|emendamento|modifica|aggiornamento)\b',
            r'\b(?:variación|enmienda|modificación|actualización)\b',
            # Types spécifiques
            r'\b(?:type i[ab]?|type ii|major|minor)\s+(?:variation|change)\b',
            r'\b(?:grouping|worksharing|urgent safety restriction)\b',
        ],

        'notice': [
            # Multilingue
            r'\b(?:notice|notification|announcement|bulletin|advisory)\b',
            r'\b(?:avis|notification|annonce|bulletin|communiqué)\b',
            r'\b(?:mitteilung|benachrichtigung|ankündigung|bekanntmachung)\b',
            r'\b(?:avviso|notifica|annuncio|bollettino|comunicato)\b',
            r'\b(?:aviso|notificación|anuncio|boletín|comunicado)\b',
            # Types spécifiques
            r'\b(?:public notice|legal notice|safety notice)\b',
            r'\b(?:dear healthcare professional|dhcp|direct healthcare professional communication|dhpc)\b',
        ],

        'report': [
            # Multilingue
            r'\b(?:report|assessment|evaluation|analysis|study)\b',
            r'\b(?:rapport|évaluation|analyse|étude|bilan)\b',
            r'\b(?:bericht|bewertung|analyse|studie|gutachten)\b',
            r'\b(?:rapporto|relazione|valutazione|analisi|studio)\b',
            r'\b(?:informe|reporte|evaluación|análisis|estudio)\b',
            # Types spécifiques
            r'\b(?:assessment report|evaluation report|inspection report|audit report)\b',
            r'\b(?:par|public assessment report|epar|european public assessment report)\b',
            r'\b(?:psur|periodic safety update report|pbrer|dsur)\b',
        ],

        'template': [
            # Multilingue
            r'\b(?:template|form|format|model|example)\b',
            r'\b(?:modèle|formulaire|format|exemple|gabarit)\b',
            r'\b(?:vorlage|formular|muster|beispiel)\b',
            r'\b(?:modello|modulo|formato|esempio)\b',
            r'\b(?:plantilla|formulario|formato|modelo|ejemplo)\b',
            # Termes spécifiques
            r'\b(?:application form|submission template|reporting template)\b',
        ],

        'manual': [
            # Multilingue
            r'\b(?:manual|handbook|compendium|reference|instructions)\b',
            r'\b(?:manuel|guide pratique|compendium|référence|instructions)\b',
            r'\b(?:handbuch|leitfaden|kompendium|referenz|anweisungen)\b',
            r'\b(?:manuale|guida pratica|compendio|riferimento|istruzioni)\b',
            r'\b(?:manual|guía práctica|compendio|referencia|instrucciones)\b',
            # Types spécifiques
            r'\b(?:user manual|reference manual|training manual|operation manual)\b',
        ],

        'specification': [
            # Multilingue
            r'\b(?:specification|spec|requirement|standard|criteria)\b',
            r'\b(?:spécification|exigence|norme|critère|cahier des charges)\b',
            r'\b(?:spezifikation|anforderung|standard|kriterium)\b',
            r'\b(?:specifica|requisito|standard|criterio)\b',
            r'\b(?:especificación|requisito|estándar|criterio)\b',
            # Termes pharmaceutiques
            r'\b(?:pharmacopoeia|pharmacopée|monograph|general chapter)\b',
        ],

        'circular': [
            # Multilingue
            r'\b(?:circular|memo|memorandum|internal communication)\b',
            r'\b(?:circulaire|mémo|mémorandum|communication interne)\b',
            r'\b(?:rundschreiben|memo|memorandum|interne mitteilung)\b',
            r'\b(?:circolare|promemoria|memorandum|comunicazione interna)\b',
            r'\b(?:circular|memorando|memorándum|comunicación interna)\b',
        ],
    }

    def __init__(self):
        self.supported_types = {
            'application/pdf': self._extract_from_pdf,
            'application/msword': self._extract_from_doc,
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document': self._extract_from_docx,
            'text/plain': self._extract_from_txt,
            'text/html': self._extract_from_html,
            'application/rtf': self._extract_from_rtf,
        }

    def extract_metadata(self, document: Document) -> DocumentExtractionLog:
        """Point d'entrée principal pour l'extraction de métadonnées"""
        start_time = timezone.now()

        # Créer le log d'extraction
        extraction_log = DocumentExtractionLog.objects.create(
            document=document,
            scraping_date=start_time,
            url=document.url_source,
            file_type=self._get_file_type(document.file.name),
            context=self._detect_context(document.file.name)
        )

        try:
            # Extraire le texte du fichier
            text_content = self._extract_text_content(document)
            document.text_content = text_content
            document.file_size = document.file.size
            document.file_type = self._get_file_type(document.file.name)

            # Extraire les métadonnées
            metadata = self._extract_all_metadata(text_content, document.file.name)

            # Appliquer les métadonnées au document
            self._apply_metadata_to_document(document, metadata)

            # Sauvegarder les informations dans le log
            self._save_extraction_log(extraction_log, metadata, start_time)

            # Mettre à jour le statut du document
            document.status = 'metadata_extracted'
            document.save()

            logger.info(f"Métadonnées extraites avec succès pour {document.title}")

        except Exception as e:
            extraction_log.extraction_status = 'failed'
            extraction_log.extraction_notes = str(e)
            extraction_log.save()

            logger.error(f"Erreur lors de l'extraction de métadonnées pour {document.title}: {e}")
            raise

        return extraction_log

    def _get_file_type(self, filename: str) -> str:
        """Détecter le type de fichier"""
        mime_type, _ = mimetypes.guess_type(filename)
        extension = Path(filename).suffix.lower()

        type_mapping = {
            '.pdf': 'pdf',
            '.doc': 'doc',
            '.docx': 'docx',
            '.txt': 'txt',
            '.html': 'html',
            '.htm': 'html',
            '.rtf': 'rtf',
        }

        return type_mapping.get(extension, 'unknown')

    def _detect_context(self, filename: str) -> str:
        """Détecter le contexte du document basé sur le nom de fichier"""
        filename_lower = filename.lower()

        if any(word in filename_lower for word in ['pharma', 'drug', 'medicine', 'medicament', 'pharmaceutical']):
            return 'pharma'
        elif any(word in filename_lower for word in ['legal', 'law', 'juridique', 'droit', 'legislation']):
            return 'juridique'
        elif any(word in filename_lower for word in ['government', 'gov', 'gouvernement', 'ministere', 'ministry']):
            return 'gouvernement'
        elif any(word in filename_lower for word in ['medical', 'health', 'medical', 'sante', 'clinical']):
            return 'medical'
        elif any(word in filename_lower for word in ['research', 'study', 'recherche', 'etude', 'trial']):
            return 'research'
        else:
            return 'pharma'  # Défaut pour le contexte pharmaceutique

    def _extract_text_content(self, document: Document) -> str:
        """Extraire le contenu textuel du fichier"""
        file_path = document.file.path
        mime_type, _ = mimetypes.guess_type(file_path)

        if mime_type in self.supported_types:
            return self.supported_types[mime_type](file_path)
        else:
            raise ValueError(f"Type de fichier non supporté: {mime_type}")

    def _extract_from_pdf(self, file_path: str) -> str:
        """Extraire le texte d'un fichier PDF"""
        text = ""
        try:
            with open(file_path, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)
                for page in pdf_reader.pages:
                    text += page.extract_text() + "\n"
        except Exception as e:
            logger.error(f"Erreur lors de l'extraction PDF: {e}")
            raise
        return text

    def _extract_from_docx(self, file_path: str) -> str:
        """Extraire le texte d'un fichier DOCX"""
        try:
            doc = docx.Document(file_path)
            text = "\n".join([paragraph.text for paragraph in doc.paragraphs])
            return text
        except Exception as e:
            logger.error(f"Erreur lors de l'extraction DOCX: {e}")
            raise

    def _extract_from_doc(self, file_path: str) -> str:
        """Extraire le texte d'un fichier DOC (version limitée)"""
        raise NotImplementedError("Extraction des fichiers .doc pas encore implémentée")

    def _extract_from_txt(self, file_path: str) -> str:
        """Extraire le texte d'un fichier TXT"""
        try:
            with open(file_path, 'rb') as file:
                raw_data = file.read()
                encoding = chardet.detect(raw_data)['encoding'] or 'utf-8'

            with open(file_path, 'r', encoding=encoding) as file:
                return file.read()
        except Exception as e:
            logger.error(f"Erreur lors de l'extraction TXT: {e}")
            raise

    def _extract_from_html(self, file_path: str) -> str:
        """Extraire le texte d'un fichier HTML"""
        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                soup = BeautifulSoup(file.read(), 'html.parser')
                return soup.get_text()
        except Exception as e:
            logger.error(f"Erreur lors de l'extraction HTML: {e}")
            raise

    def _extract_from_rtf(self, file_path: str) -> str:
        """Extraire le texte d'un fichier RTF (implémentation basique)"""
        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                content = file.read()
                text = re.sub(r'\\[a-z]+\d*', '', content)
                text = re.sub(r'[{}]', '', text)
                return text
        except Exception as e:
            logger.error(f"Erreur lors de l'extraction RTF: {e}")
            raise

    def _extract_all_metadata(self, text: str, filename: str) -> Dict:
        """Extraire toutes les métadonnées du texte avec stratégie améliorée"""
        # Utiliser différentes portions du texte pour différentes métadonnées
        text_start = text[:10000]  # Début pour titre et métadonnées principales
        text_sample = text[:5000]  # Échantillon pour langue
        text_full = text  # Texte complet pour source et autres

        # Détecter la langue en premier
        language = self._detect_language(text_sample)

        metadata = {
            'title': self._extract_title(text_start, filename),
            'date': self._extract_date(text_full),  # Chercher dans tout le texte
            'version': self._extract_version(text_start),
            'language': language,
            'source': self._extract_source(text_full),
            'country': self._extract_country(text_full, language[0]),
            'document_type': self._extract_document_type(text_start, filename),
        }

        metadata['confidence'] = self._calculate_confidence_scores(metadata, text_sample)

        return metadata

    def _extract_title(self, text: str, filename: str) -> Tuple[str, int]:
        """
        Extraire le titre du document avec approche ultra-robuste

        Résout spécifiquement le problème des phrases de corps de texte
        extraites à la place des vrais titres.
        """
        confidence = 0
        title = ""

        # Nettoyer et préparer le texte
        text_lines = [line.strip() for line in text.split('\n') if line.strip()]

        # ÉTAPE 1: Patterns pour MÉTADONNÉES (à ignorer absolument)
        METADATA_PATTERNS = [
            r'^\d{1,2}\s+\w+\s+\d{4}$',  # Dates (04 June 2025)
            r'^EMA/\w+/\d+',  # Références EMA (EMA/307181/2017)
            r'^FDA[/-]\d+',  # Références FDA
            r'^ICH\s+[A-Z]\d+',  # Références ICH
            r'^ANSM\s*-',  # En-têtes ANSM
            r'^version\s+\d+',  # Versions (Version 5)
            r'^step\s+\d+',  # Steps ICH
            r'^draft\s+guidance',  # Draft guidance
            r'^guidance\s+for\s+industry',  # Guidance for industry
            r'^\w+\s+management$',  # Départements (Information Management)
            r'^committee\s+for',  # Comités
            r'^direction\s+de',  # Directions (français)
            r'^référence\s*:',  # Références
            r'^CDER/CBER$',  # Centres FDA
            r'^page\s+\d+',  # Numéros de page
            r'^table\s+of\s+contents',  # Table des matières
            r'^\d+\.\d+\.\d+',  # Numéros de version
            r'^copyright',  # Copyright
            r'^confidential',  # Confidentiel
            r'^\d+\.\s+\w+',  # Sections numérotées (1. Introduction)
            r'^appendix\s+[A-Z]',  # Annexes
        ]

        # ÉTAPE 2: Patterns pour PHRASES DE CORPS DE TEXTE (NOUVEAU - clé du succès!)
        BODY_TEXT_PATTERNS = [
            r'^following\s+the\s+publication',  # "Following the publication..."
            r'^this\s+document\s+provides',  # "This document provides..."
            r'^this\s+guideline\s+applies',  # "This guideline applies..."
            r'^in\s+accordance\s+with',  # "In accordance with..."
            r'^the\s+purpose\s+of\s+this',  # "The purpose of this..."
            r'^it\s+should\s+be\s+noted',  # "It should be noted..."
            r'^please\s+note\s+that',  # "Please note that..."
            r'^for\s+further\s+information',  # "For further information..."
            r'^this\s+document\s+has\s+been',  # "This document has been..."
            r'^the\s+content\s+of\s+this',  # "The content of this..."
            r'^since\s+the\s+publication',  # "Since the publication..."
            r'^after\s+consultation',  # "After consultation..."
            r'^\w+\s+is\s+available',  # "Information is available..."
            r'^questions\s+concerning',  # "Questions concerning..."
            r'^comments\s+on\s+this',  # "Comments on this..."
            r'^as\s+outlined\s+in',  # "As outlined in..."
            r'^further\s+details\s+are',  # "Further details are..."
            r'^users\s+should\s+note',  # "Users should note..."
        ]

        # ÉTAPE 3: Patterns pour VRAIS TITRES (par ordre de priorité)
        TITLE_PATTERNS = [
            # 1. Titres avec mots-clés réglementaires spécifiques (PRIORITÉ MAXIMALE)
            r'^([^.\n]*(?:on-boarding|guideline|guidance|procedure|regulation|recommendation|assessment|evaluation)[^.\n]{5,150}[^.])$',

            # 2. Titres français avec mots-clés
            r'^([^.\n]*(?:recommandation|évaluation|procédure|instruction|guide)[^.\n]{5,150}[^.])$',

            # 3. Titres longs avec mots de finalité (services, system, etc.)
            r'^([A-Z][A-Za-z0-9\s\-–—(),]+(?:services|system|process|framework|protocol|standards?|requirements?|specifications?)[^.]*)$',

            # 4. Titres généraux avec bonne structure
            r'^([A-Z][A-Za-z0-9\s\-–—(),]{20,150}[^.])$',

            # 5. Titres courts mais descriptifs
            r'^([A-Z][A-Za-z0-9\s\-–—(),]{15,100})$',
        ]

        def is_metadata_line(line):
            """Vérifier si une ligne est une métadonnée à ignorer"""
            return any(re.match(pattern, line, re.IGNORECASE) for pattern in METADATA_PATTERNS)

        def is_body_text_line(line):
            """Vérifier si une ligne est du corps de texte (phrases explicatives) - CRUCIAL!"""
            return any(re.match(pattern, line, re.IGNORECASE) for pattern in BODY_TEXT_PATTERNS)

        def is_valid_title_structure(line):
            """Vérifier si la ligne a une structure de titre valide"""
            # Rejeter si se termine par "to" (phrase incomplète comme "was amended to")
            if re.search(r'\bto\s*$', line, re.IGNORECASE):
                return False

            # Rejeter si contient des références temporelles (indicateurs de texte explicatif)
            if re.search(r'\b(?:since|after|before|during|following|version\s+\d+\s+in\s+\w+\s+\d{4})', line,
                         re.IGNORECASE):
                return False

            # Rejeter si trop de virgules (souvent signe de phrase explicative)
            if line.count(',') > 3:
                return False

            # Rejeter si contient "was/were" (souvent du texte explicatif)
            if re.search(r'\b(?:was|were)\s+\w+', line, re.IGNORECASE):
                return False

            return True

        # ÉTAPE 4: Chercher le titre dans les premières lignes
        candidates = []

        for i, line in enumerate(text_lines[:25]):  # Regarder les 25 premières lignes

            # Vérifications successives (ordre important!)
            if is_metadata_line(line):
                continue

            if is_body_text_line(line):  # NOUVEAU - évite le problème principal!
                continue

            if len(line) < 10 or len(line) > 250:
                continue

            if not is_valid_title_structure(line):
                continue

            # Essayer chaque pattern
            for pattern_idx, pattern in enumerate(TITLE_PATTERNS):
                try:
                    match = re.match(pattern, line, re.IGNORECASE)
                    if match:
                        potential_title = match.group(1) if match.lastindex else line

                        # Nettoyer le titre
                        potential_title = re.sub(r'\s+', ' ', potential_title).strip()
                        potential_title = potential_title.strip(' .,;:')

                        # Vérifications finales de qualité
                        if 10 <= len(potential_title) <= 200:
                            # Calculer la confiance
                            calc_confidence = 95 - (pattern_idx * 5)

                            # Bonus majeur pour position très élevée
                            if i <= 5:
                                calc_confidence += 15
                            elif i <= 10:
                                calc_confidence += 8

                            # Bonus pour mots-clés réglementaires
                            regulatory_keywords = [
                                'guideline', 'guidance', 'procedure', 'regulation', 'directive',
                                'recommendation', 'on-boarding', 'introduction', 'assessment',
                                'evaluation', 'recommandation', 'évaluation', 'procédure'
                            ]
                            if any(kw in potential_title.lower() for kw in regulatory_keywords):
                                calc_confidence += 12

                            # Bonus pour mots-clés de finalité
                            finality_keywords = ['services', 'system', 'process', 'framework', 'protocol', 'standards',
                                                 'requirements']
                            if any(kw in potential_title.lower() for kw in finality_keywords):
                                calc_confidence += 8

                            # Bonus pour structure typique des titres
                            if re.search(r'\b(?:of|to|for|and|or|pour|de|des|du)\b', potential_title, re.IGNORECASE):
                                calc_confidence += 3

                            # Malus pour éléments suspects
                            if re.search(r'\d{4}|\w+@\w+\.\w+|page\s+\d+|version\s+\d+', potential_title,
                                         re.IGNORECASE):
                                calc_confidence -= 15

                            calc_confidence = max(40, min(98, calc_confidence))

                            candidates.append((potential_title, calc_confidence, i, pattern_idx))

                except Exception as e:
                    logger.debug(f"Erreur avec le pattern {pattern}: {e}")
                    continue

        # ÉTAPE 5: Sélectionner le meilleur candidat
        if candidates:
            # Trier par confiance, puis par position
            candidates.sort(key=lambda x: (x[1], -x[2]), reverse=True)

            # Si plusieurs candidats avec scores proches, préférer le plus descriptif
            best_candidates = [c for c in candidates if c[1] >= candidates[0][1] - 5]

            if len(best_candidates) > 1:
                # Préférer le plus descriptif
                scored_candidates = []
                for candidate in best_candidates:
                    title_text = candidate[0]
                    descriptiveness_score = len(title_text)

                    # Bonus pour mots-clés importants
                    if any(kw in title_text.lower() for kw in ['guideline', 'guidance', 'procedure', 'on-boarding']):
                        descriptiveness_score += 50

                    scored_candidates.append((candidate, descriptiveness_score))

                best_candidate = max(scored_candidates, key=lambda x: x[1])[0]
                title, confidence, position, pattern_used = best_candidate
            else:
                title, confidence, position, pattern_used = candidates[0]

        else:
            # Fallback intelligent
            for line in text_lines[:20]:
                if (not is_metadata_line(line) and
                        not is_body_text_line(line) and
                        is_valid_title_structure(line) and
                        15 <= len(line) <= 200 and
                        not re.match(r'^\d+\.', line)):
                    title = line.strip(' .,;:')
                    confidence = 50
                    break

            # Si toujours pas de titre, utiliser le nom de fichier
            if not title:
                title = Path(filename).stem
                title = re.sub(r'[-_]', ' ', title)
                title = re.sub(r'\s+', ' ', title).strip()
                confidence = 30

        # Log pour surveillance
        logger.info(f"Titre extrait: '{title}' (confiance: {confidence}%)")
        if confidence < 70:
            logger.warning(f"Confiance faible pour l'extraction de titre: {confidence}%")

        return title, confidence

    def _extract_date(self, text: str) -> Tuple[Optional[date], int]:
        """Extraire la date du document avec détection améliorée"""
        # 1. Normaliser le texte
        normalized = unicodedata.normalize('NFKD', text)
        normalized = re.sub(r'[^\w\s/.-]', ' ', normalized)  # Conserver les séparateurs de date
        normalized = re.sub(r'\s+', ' ', normalized).lower()

        # 2. Découper en header et body
        header = normalized[:2500]
        body = normalized[2500:50000]  # Limité à 50 000 caractères

        candidates = []

        # 3. Chercher avec chaque regex
        for pattern_idx, pattern in enumerate(self.DATE_PATTERNS):
            try:
                # Compiler le regex
                regex = re.compile(pattern, re.IGNORECASE)

                # Dans le header
                for match in regex.finditer(header):
                    # Prendre la chaîne complète pour les dates textuelles (patterns à partir de l'index 10)
                    if pattern_idx >= 10:  # Les patterns de dates textuelles
                        date_str = match.group(0)
                    else:
                        date_str = match.group(1) if match.lastindex else match.group(0)

                    parsed_date = self._parse_date_string(date_str)
                    if parsed_date:
                        candidates.append((parsed_date, pattern_idx, True))

                # Dans le body
                for match in regex.finditer(body):
                    if pattern_idx >= 10:  # Les patterns de dates textuelles
                        date_str = match.group(0)
                    else:
                        date_str = match.group(1) if match.lastindex else match.group(0)

                    parsed_date = self._parse_date_string(date_str)
                    if parsed_date:
                        candidates.append((parsed_date, pattern_idx, False))
            except Exception as e:
                logger.error(f"Erreur regex avec le pattern {pattern}: {e}")
                continue

        # 4. Si aucun candidat, essayer une année seule
        if not candidates:
            year_match = re.search(r'\b(19[89]\d|20[0-3]\d)\b', normalized)
            if year_match:
                year = int(year_match.group(0))
                return date(year, 1, 1), 40
            return None, 0

        # 5. Calculer les scores de confiance
        scored_candidates = []
        current_year = datetime.now().year

        for date_val, pattern_idx, is_header in candidates:
            # Score de base basé sur la position du pattern
            base_score = 100 - pattern_idx
            # Bonus pour les dates dans le header
            if is_header:
                base_score += 20

            # Pénalité pour dates invraisemblables
            if date_val.year < 1980 or date_val.year > current_year + 1:
                base_score -= 30
            # Bonus pour les dates récentes
            elif current_year - 5 <= date_val.year <= current_year:
                base_score += 10

            scored_candidates.append((date_val, min(100, max(30, base_score))))

            # 6. Trouver le meilleur candidat
            best_candidate = max(scored_candidates, key=lambda x: x[1])
        return best_candidate

    def _month_name_to_number(self, month_str: str) -> int:
        """Convertir un nom de mois en numéro"""
        month_str = month_str.lower().strip('.')

        month_map = {
            # Anglais
            'january': 1, 'jan': 1,
            'february': 2, 'feb': 2,
            'march': 3, 'mar': 3,
            'april': 4, 'apr': 4,
            'may': 5,
            'june': 6, 'jun': 6,
            'july': 7, 'jul': 7,
            'august': 8, 'aug': 8,
            'september': 9, 'sep': 9, 'sept': 9,
            'october': 10, 'oct': 10,
            'november': 11, 'nov': 11,
            'december': 12, 'dec': 12,
            # Français
            'janvier': 1, 'janv': 1,
            'février': 2, 'fevrier': 2, 'fév': 2, 'févr': 2, 'fev': 2,
            'mars': 3,
            'avril': 4, 'avr': 4,
            'mai': 5,
            'juin': 6,
            'juillet': 7, 'juil': 7,
            'août': 8, 'aout': 8,
            'septembre': 9, 'sept': 9,
            'octobre': 10,
            'novembre': 11,
            'décembre': 12, 'decembre': 12, 'déc': 12, 'dec': 12,
            # Espagnol
            'enero': 1, 'ene': 1,
            'febrero': 2, 'feb': 2,
            'marzo': 3, 'mar': 3,
            'abril': 4, 'abr': 4,
            'mayo': 5, 'may': 5,
            'junio': 6, 'jun': 6,
            'julio': 7, 'jul': 7,
            'agosto': 8, 'ago': 8,
            'septiembre': 9, 'setiembre': 9, 'sep': 9, 'set': 9,
            'octubre': 10, 'oct': 10,
            'noviembre': 11, 'nov': 11,
            'diciembre': 12, 'dic': 12,
            # Allemand
            'januar': 1, 'jan': 1,
            'februar': 2, 'feb': 2,
            'märz': 3, 'marz': 3, 'mar': 3,
            'april': 4, 'apr': 4,
            'mai': 5,
            'juni': 6, 'jun': 6,
            'juli': 7, 'jul': 7,
            'august': 8, 'aug': 8,
            'september': 9, 'sep': 9, 'sept': 9,
            'oktober': 10, 'okt': 10,
            'november': 11, 'nov': 11,
            'dezember': 12, 'dez': 12,
            # Italien
            'gennaio': 1, 'gen': 1,
            'febbraio': 2, 'feb': 2,
            'marzo': 3, 'mar': 3,
            'aprile': 4, 'apr': 4,
            'maggio': 5, 'mag': 5,
            'giugno': 6, 'giu': 6,
            'luglio': 7, 'lug': 7,
            'agosto': 8, 'ago': 8,
            'settembre': 9, 'set': 9,
            'ottobre': 10, 'ott': 10,
            'novembre': 11, 'nov': 11,
            'dicembre': 12, 'dic': 12,
            # Néerlandais
            'januari': 1, 'jan': 1,
            'februari': 2, 'feb': 2,
            'maart': 3, 'mrt': 3,
            'april': 4, 'apr': 4,
            'mei': 5,
            'juni': 6, 'jun': 6,
            'juli': 7, 'jul': 7,
            'augustus': 8, 'aug': 8,
            'september': 9, 'sep': 9, 'sept': 9,
            'oktober': 10, 'okt': 10,
            'november': 11, 'nov': 11,
            'december': 12, 'dec': 12,
        }

        return month_map.get(month_str, 0)

    def _parse_date_string(self, date_str: str) -> Optional[date]:
        """Parser une chaîne de date avec plusieurs formats"""
        if not date_str or len(date_str) < 6:
            return None

        # Nettoyer la chaîne
        date_str = date_str.strip().lower()
        date_str = re.sub(r'[^\w\s/.-]', ' ', date_str)
        date_str = re.sub(r'\s+', ' ', date_str)

        # Formats de date à essayer
        date_formats = [
            # ISO
            '%Y-%m-%d', '%Y/%m/%d', '%Y.%m.%d', '%Y_%m_%d',
            # Européen
            '%d/%m/%Y', '%d-%m-%Y', '%d.%m.%Y', '%d %m %Y',
            '%d/%m/%y', '%d-%m-%y', '%d.%m.%y',
            # Américain
            '%m/%d/%Y', '%m-%d-%Y', '%m.%d.%Y',
            '%m/%d/%y', '%m-%d-%y',
            # Année seule
            '%Y',
        ]

        for fmt in date_formats:
            try:
                return datetime.strptime(date_str, fmt).date()
            except ValueError:
                continue

        # Essayer de parser avec les noms de mois
        return self._parse_date_with_month_names(date_str)

    def _parse_date_with_month_names(self, date_str: str) -> Optional[date]:
        """Parser les dates avec noms de mois multilingues - AMÉLIORATION"""
        # Nouveau mapping multilingue plus complet
        month_map = {
            # Anglais
            'january': 1, 'jan': 1,
            'february': 2, 'feb': 2,
            'march': 3, 'mar': 3,
            'april': 4, 'apr': 4,
            'may': 5,
            'june': 6, 'jun': 6,
            'july': 7, 'jul': 7,
            'august': 8, 'aug': 8,
            'september': 9, 'sep': 9, 'sept': 9,
            'october': 10, 'oct': 10,
            'november': 11, 'nov': 11,
            'december': 12, 'dec': 12,

            # Français
            'janvier': 1, 'janv': 1, 'jan': 1,
            'février': 2, 'fevrier': 2, 'févr': 2, 'fev': 2, 'fév': 2, 'feb': 2,
            'mars': 3, 'mar': 3,
            'avril': 4, 'avr': 4, 'av': 4,
            'mai': 5, 'may': 5,
            'juin': 6, 'jun': 6,
            'juillet': 7, 'juil': 7, 'jul': 7,
            'août': 8, 'aout': 8, 'aoû': 8, 'aug': 8,
            'septembre': 9, 'sept': 9, 'sep': 9,
            'octobre': 10, 'oct': 10,
            'novembre': 11, 'nov': 11,
            'décembre': 12, 'decembre': 12, 'déc': 12, 'dec': 12,

            # Espagnol
            'enero': 1, 'ene': 1,
            'febrero': 2, 'feb': 2,
            'marzo': 3, 'mar': 3,
            'abril': 4, 'abr': 4,
            'mayo': 5, 'may': 5,
            'junio': 6, 'jun': 6,
            'julio': 7, 'jul': 7,
            'agosto': 8, 'ago': 8,
            'septiembre': 9, 'setiembre': 9, 'sep': 9, 'set': 9,
            'octubre': 10, 'oct': 10,
            'noviembre': 11, 'nov': 11,
            'diciembre': 12, 'dic': 12,

            # Allemand
            'januar': 1, 'jan': 1,
            'februar': 2, 'feb': 2,
            'märz': 3, 'marz': 3, 'mar': 3,
            'april': 4, 'apr': 4,
            'mai': 5,
            'juni': 6, 'jun': 6,
            'juli': 7, 'jul': 7,
            'august': 8, 'aug': 8,
            'september': 9, 'sep': 9, 'sept': 9,
            'oktober': 10, 'okt': 10,
            'november': 11, 'nov': 11,
            'dezember': 12, 'dez': 12,

            # Italien
            'gennaio': 1, 'gen': 1,
            'febbraio': 2, 'feb': 2,
            'marzo': 3, 'mar': 3,
            'aprile': 4, 'apr': 4,
            'maggio': 5, 'mag': 5,
            'giugno': 6, 'giu': 6,
            'luglio': 7, 'lug': 7,
            'agosto': 8, 'ago': 8,
            'settembre': 9, 'set': 9,
            'ottobre': 10, 'ott': 10,
            'novembre': 11, 'nov': 11,
            'dicembre': 12, 'dic': 12,

            # Néerlandais
            'januari': 1, 'jan': 1,
            'februari': 2, 'feb': 2,
            'maart': 3, 'mrt': 3,
            'april': 4, 'apr': 4,
            'mei': 5,
            'juni': 6, 'jun': 6,
            'juli': 7, 'jul': 7,
            'augustus': 8, 'aug': 8,
            'september': 9, 'sep': 9, 'sept': 9,
            'oktober': 10, 'okt': 10,
            'november': 11, 'nov': 11,
            'december': 12, 'dec': 12,
        }

        # Essayer plusieurs formats
        formats_to_try = [
            r'(\d{1,2})\s+(\w+)\s+(\d{4})',  # 29 November 2016
            r'(\w+)\s+(\d{1,2}),?\s+(\d{4})',  # November 29, 2016
            r'(\d{1,2})[-/\.](\w+)[-/\.](\d{4})',  # 29-Nov-2016
        ]

        for fmt in formats_to_try:
            match = re.search(fmt, date_str, re.IGNORECASE)
            if match:
                groups = match.groups()
                if len(groups) == 3:
                    day_str, month_str, year_str = groups

                    # Nettoyer les chaînes
                    month_str = month_str.lower().strip(' .')

                    # Trouver le numéro du mois
                    month_num = month_map.get(month_str, 0)
                    if month_num == 0:
                        # Essayer avec les 3 premiers caractères
                        short_month = month_str[:3]
                        month_num = month_map.get(short_month, 0)

                    if month_num > 0:
                        try:
                            day = int(day_str)
                            year = int(year_str)
                            return date(year, month_num, day)
                        except ValueError:
                            continue

        return None
    def _extract_version(self, text: str) -> Tuple[str, int]:
        """Extraire la version du document avec patterns améliorés"""
        confidence = 0
        version = ""
        candidates = []

        # Nettoyer le texte
        text_lines = text[:3000].split('\n')

        for pattern in self.VERSION_PATTERNS:
            try:
                # Chercher dans chaque ligne
                for i, line in enumerate(text_lines[:100]):
                    matches = re.finditer(pattern, line, re.IGNORECASE)
                    for match in matches:
                        version_str = match.group(1).strip()

                        # Calculer la confiance
                        calc_confidence = 60
                        if i < 20:  # Dans les premières lignes
                            calc_confidence += 20
                        if 'version' in line.lower() or 'v.' in line.lower():
                            calc_confidence += 10
                        if re.match(r'^\d+\.\d+', version_str):  # Format X.Y
                            calc_confidence += 5

                        candidates.append((version_str, calc_confidence))

            except Exception as e:
                logger.debug(f"Erreur extraction version: {e}")
                continue

        # Sélectionner la meilleure version
        if candidates:
            candidates.sort(key=lambda x: x[1], reverse=True)
            version, confidence = candidates[0]

        return version, confidence

    def _detect_language(self, text: str) -> Tuple[str, int]:
        """Détecter la langue du document avec méthode améliorée"""
        try:
            # Nettoyer le texte pour une meilleure détection
            sample_text = re.sub(r'[^\w\s]', ' ', text[:2000])
            sample_text = re.sub(r'\s+', ' ', sample_text)
            sample_text = sample_text.strip()

            if len(sample_text) < 50:
                return 'en', 30

            # Première tentative
            detected = detect(sample_text)

            # Vérifier la confiance avec un échantillon plus large si nécessaire
            if detected in self.LANGUAGE_MAPPING:
                # Confirmer avec un échantillon plus large
                larger_sample = re.sub(r'[^\w\s]', ' ', text[:5000])
                detected_confirm = detect(larger_sample)

                if detected == detected_confirm:
                    confidence = 90
                else:
                    # Prendre le résultat du plus grand échantillon
                    detected = detected_confirm
                    confidence = 75

                return detected, confidence

            return 'en', 40

        except Exception as e:
            logger.warning(f"Erreur détection langue: {e}")
            return 'en', 30

    def _extract_source(self, text: str) -> Tuple[str, int]:
        """Extraire la source du document avec méthode améliorée"""
        source_scores = {}

        # Analyser tout le texte pour chaque source
        for source_name, patterns in self.SOURCE_PATTERNS.items():
            score = 0
            matches = 0

            for pattern in patterns:
                # Compter les occurrences
                found = re.findall(pattern, text, re.IGNORECASE)
                if found:
                    matches += len(found)
                    # Bonus pour les matches en début de document
                    early_matches = re.findall(pattern, text[:2000], re.IGNORECASE)
                    score += len(found) * 10 + len(early_matches) * 5

            if matches > 0:
                source_scores[source_name] = (score, matches)

        # Sélectionner la source avec le meilleur score
        if source_scores:
            best_source = max(source_scores.items(), key=lambda x: x[1][0])
            source = best_source[0]
            score, matches = best_source[1]

            # Calculer la confiance
            confidence = min(95, 50 + (matches * 5) + (score // 10))

            return source, confidence

        return "", 0

    def _extract_country(self, text: str, detected_language: str) -> Tuple[str, int]:
        """Extraire le pays avec détection améliorée"""
        country_scores = {}

        # Analyser le texte pour chaque pays
        for country_name, patterns in self.COUNTRY_PATTERNS.items():
            score = 0
            matches = 0

            for pattern in patterns:
                found = re.findall(pattern, text[:10000], re.IGNORECASE)
                if found:
                    matches += len(found)
                    # Bonus pour les mentions explicites
                    if country_name.lower() in pattern.lower():
                        score += len(found) * 15
                    else:
                        score += len(found) * 10

            if matches > 0:
                country_scores[country_name] = (score, matches)

        # Sélectionner le pays avec le meilleur score
        if country_scores:
            # Vérifier s'il y a plusieurs pays mentionnés
            if len(country_scores) > 1:
                # Si EU est mentionné avec d'autres pays européens, préférer EU
                if 'EU' in country_scores and any(c in country_scores for c in ['France', 'Germany', 'Italy', 'Spain']):
                    total_eu_mentions = sum(country_scores[c][1] for c in country_scores if c != 'EU')
                    if country_scores['EU'][1] > 0 or total_eu_mentions >= 3:
                        return 'EU', 85

            best_country = max(country_scores.items(), key=lambda x: x[1][0])
            country = best_country[0]
            score, matches = best_country[1]

            # Calculer la confiance
            confidence = min(90, 50 + (matches * 5) + (score // 20))

            return country, confidence

        # Fallback basé sur la langue détectée
        if detected_language in self.EUROPEAN_LANGUAGES:
            return 'EU', 60

        return "", 0

    def _extract_document_type(self, text: str, filename: str) -> Tuple[str, int]:
        """Extraire le type de document avec détection améliorée"""
        type_scores = {}

        # Combiner l'analyse du texte et du nom de fichier
        combined_text = filename.lower() + " " + text[:3000].lower()

        for type_name, patterns in self.DOCUMENT_TYPE_PATTERNS.items():
            score = 0

            for pattern in patterns:
                # Chercher dans le texte combiné
                matches = re.findall(pattern.lower(), combined_text)
                if matches:
                    score += len(matches) * 10
                    # Bonus si trouvé dans le nom de fichier
                    if pattern.lower() in filename.lower():
                        score += 20

            if score > 0:
                type_scores[type_name] = score

        # Sélectionner le type avec le meilleur score
        if type_scores:
            best_type = max(type_scores.items(), key=lambda x: x[1])
            doc_type = best_type[0]
            score = best_type[1]

            # Calculer la confiance
            confidence = min(90, 50 + (score // 5))

            return doc_type, confidence

        return 'autres', 30

    def _calculate_confidence_scores(self, metadata: Dict, text: str) -> Dict[str, int]:
        """Calculer les scores de confiance pour chaque métadonnée"""
        scores = {}

        for key, value in metadata.items():
            if key == 'confidence':
                continue

            if isinstance(value, tuple):
                scores[key] = value[1]
            else:
                scores[key] = 50 if value else 0

        # Score global basé sur la moyenne pondérée
        weights = {
            'title': 0.25,
            'date': 0.20,
            'source': 0.20,
            'language': 0.15,
            'country': 0.10,
            'document_type': 0.10
        }

        global_score = sum(scores.get(k, 0) * w for k, w in weights.items())
        scores['global'] = int(global_score)

        return scores

    def _apply_metadata_to_document(self, document: Document, metadata: Dict):
        """Appliquer les métadonnées extraites au document"""
        if metadata['title'][0] and not document.title_manually_edited:
            document.auto_extracted_title = metadata['title'][0]
            if not document.title:
                document.title = metadata['title'][0]

        if metadata['date'][0] and not document.date_manually_edited:
            document.auto_extracted_date = metadata['date'][0]
            if not document.publication_date:
                document.publication_date = metadata['date'][0]

        if metadata['language'][0] and not document.language_manually_edited:
            document.auto_extracted_language = metadata['language'][0]
            if document.language == 'auto':
                document.language = metadata['language'][0]

        if metadata['version'][0]:
            document.auto_extracted_version = metadata['version'][0]
            if not document.version:
                document.version = metadata['version'][0]

        document.auto_extracted_source = metadata['source'][0]
        document.auto_extracted_country = metadata['country'][0]

        if metadata['document_type'][0] and not document.document_type:
            document.document_type = metadata['document_type'][0]

        document.extraction_confidence = metadata['confidence']

        document.save()

    def _save_extraction_log(self, log: DocumentExtractionLog, metadata: Dict, start_time):
        """Sauvegarder les informations d'extraction dans le log"""
        processing_time = (timezone.now() - start_time).total_seconds()

        log.extracted_title = metadata['title'][0]
        log.extracted_date = metadata['date'][0]
        log.extracted_language = metadata['language'][0]
        log.extracted_country = metadata['country'][0]
        log.extracted_source = metadata['source'][0]
        log.extracted_version = metadata['version'][0]

        log.confidence_title = metadata['confidence']['title']
        log.confidence_date = metadata['confidence']['date']
        log.confidence_language = metadata['confidence']['language']
        log.confidence_source = metadata['confidence']['source']

        log.processing_time = processing_time
        log.extraction_status = 'success'
        log.extraction_notes = f"Extraction réussie en {processing_time:.2f}s"

        log.save()

    def test_extraction(self, test_type: str = 'all') -> Dict:
        """Tester l'extraction sur des exemples"""
        results = {}

        if test_type in ['all', 'date']:
            results['date'] = self.test_date_extraction()

        if test_type in ['all', 'country']:
            results['country'] = self.test_country_extraction()

        if test_type in ['all', 'source']:
            results['source'] = self.test_source_extraction()

        return results

    def test_date_extraction(self, test_texts: List[str] = None) -> Dict:
        """Tester l'extraction de dates sur des textes d'exemple"""
        results = []

        test_cases = test_texts or [
            "Published on 15 March 2024",
            "Publié le 15 mars 2024",
            "Veröffentlicht am 15. März 2024",
            "Fecha: 15 de marzo de 2024",
            "Data: 15 marzo 2024",
            "Datum: 15 maart 2024",
            "15 января 2024",
            "Version 2.1 du 15/03/2024",
            "2024-03-15",
            "15.03.2024",
            "03/15/2024",
            "15/03/2024",
            "Effective date: January 15, 2024",
            "Revision dated 15th January 2024",
            "Approved on 15 Jan 2024",
            "Issued: 15-01-2024",
            "Date of publication: 15.01.2024",
            "Last updated on March 15, 2024",
            "Valid from 15/03/2024",
            "EMA/123456/2024 - 15 March 2024"
        ]

        for test_text in test_cases:
            date, confidence = self._extract_date(test_text)
            results.append({
                'text': test_text,
                'extracted_date': date.isoformat() if date else None,
                'confidence': confidence,
                'success': date is not None
            })

        success_rate = sum(1 for r in results if r['success']) / len(results) * 100

        return {
            'test_results': results,
            'success_rate': success_rate,
            'total_tests': len(results),
            'successful_extractions': sum(1 for r in results if r['success'])
        }

    def test_country_extraction(self) -> Dict:
        """Tester l'extraction de pays"""
        test_cases = [
            ("This guideline applies to all EU member states", "EU"),
            ("FDA guidance for industry", "USA"),
            ("ANSM - Agence nationale de sécurité du médicament", "France"),
            ("MHRA regulatory update", "UK"),
            ("Issued by Health Canada", "Canada"),
            ("Swissmedic guideline", "Switzerland"),
            ("BfArM Bekanntmachung", "Germany"),
            ("AIFA - Agenzia Italiana del Farmaco", "Italy"),
            ("Agencia Española de Medicamentos", "Spain"),
            ("European Medicines Agency guideline", "EU"),
        ]

        results = []
        for text, expected in test_cases:
            country, confidence = self._extract_country(text, 'en')
            results.append({
                'text': text,
                'expected': expected,
                'extracted': country,
                'confidence': confidence,
                'success': country == expected
            })

        success_rate = sum(1 for r in results if r['success']) / len(results) * 100

        return {
            'test_results': results,
            'success_rate': success_rate
        }

    def test_source_extraction(self) -> Dict:
        """Tester l'extraction de source"""
        test_cases = [
            ("EMA/CHMP/123456/2024", "EMA"),
            ("FDA Guidance for Industry", "FDA"),
            ("ICH Q10 Pharmaceutical Quality System", "ICH"),
            ("ANSM - Mise à jour réglementaire", "ANSM"),
            ("MHRA GMP Certificate", "MHRA"),
            ("WHO Technical Report Series No. 1234", "WHO"),
            ("European Pharmacopoeia 10.0", "EDQM"),
            ("Health Canada Notice", "Health Canada"),
            ("PMDA regulatory update", "PMDA"),
            ("TGA Australian regulatory guidelines", "TGA"),
        ]

        results = []
        for text, expected in test_cases:
            source, confidence = self._extract_source(text)
            results.append({
                'text': text,
                'expected': expected,
                'extracted': source,
                'confidence': confidence,
                'success': source == expected
            })

        success_rate = sum(1 for r in results if r['success']) / len(results) * 100

        return {
            'test_results': results,
            'success_rate': success_rate
        }