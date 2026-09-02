/* Participant-facing chrome, in the two languages a scenario can be generated
 * in (spec 16). Deliberately narrow: the admin console is an operator tool,
 * not part of what a session measures, and stays English-only rather than
 * doubling the size of this file for no participant-facing benefit.
 *
 * A session is monolingual end to end -- text and audio never mix languages
 * within one scenario -- so a page picks one of these tables once, from the
 * scenario's own `language` field, and never switches mid-session. */

export const LANGUAGES = ['en', 'fr'];

export const LANGUAGE_NAMES = { en: 'English', fr: 'Français' };

/* Uppercase, short: the actor `type` is an internal key (spec 11.2) rendered
 * directly in the modal head. English already reads fine verbatim; French
 * gets its own short station-console word per type. */
export const ACTOR_TYPE_LABELS = {
  en: {
    security: 'SECURITY', construction: 'CONSTRUCTION', cargo: 'CARGO',
    medical: 'MEDICAL', civilian: 'CIVILIAN', system: 'SYSTEM',
  },
  fr: {
    security: 'SÉCURITÉ', construction: 'CONSTRUCTION', cargo: 'FRET',
    medical: 'MÉDICAL', civilian: 'CIVIL', system: 'SYSTÈME',
  },
};

/* Door-state words, for the one place they leak into free text rather than
 * the canvas: the "CONFIRMED —" toast (game.js), built server-side from the
 * DoorState literal ("open"/"closed", spec 11.1) which is protocol, not
 * prose, and so stays English at the wire regardless of scenario language. */
export const DOOR_STATE_WORDS = {
  en: { open: 'open', closed: 'closed' },
  fr: { open: 'ouverte', closed: 'fermée' },
};

const STRINGS = {
  en: {
    // home.js
    stationHeader: (version) => `Station — ${version} — practice mode, nothing is recorded`,
    beginShift: 'Begin a shift',
    participant: 'Participant',
    participantPlaceholder: 'name or code',
    scenario: 'Scenario',
    startShift: 'Start shift',
    beforeYouStart: 'Before you start',
    instructions: [
      '<strong>Click a door to open or close it.</strong> Green is open, red is closed. Try every one now — once the shift starts the clock runs and never pauses.',
      '<strong>Two places have no door of their own.</strong> Find them. They are drawn as a break in the wall rather than a bar.',
      '<strong>Work through the printed sector cards against this map.</strong> Which doors bound a sector is the one thing you cannot read off the station, and it is not what the session is measuring.',
      '<strong>You get each message once.</strong> No history, no replay, no pause. Radio messages are spoken and have no transcript. Pen and paper are allowed.',
      'Pressing <strong>Start shift</strong> resets every door to its standard position and turns the sound on.',
    ],
    bankEmpty: '— the bank is empty —',
    someUnplayable: (n) => `${n} scenario(s) in the bank, none playable. `,
    openAdmin: 'Open admin',
    toSeeWhy: ' to see why.',
    noScenariosYet: 'No scenarios yet. ',
    generateOne: 'Generate one',
    scenarioOption: (s) => `${s.name} — ${Math.round(s.duration_seconds / 60)} min`,
    describe: (c) =>
      `${c.messages} messages, ${c.threads} threads, ${c.radio_messages} spoken. Station ${c.station_version}.`
      + (c.tunables_match ? '' : ' Validated against different difficulty settings.'),
    soundFailed: (msg) => `Sound could not be started (${msg}). `
      + 'A session without audio is void, so it will not begin. '
      + 'Check the browser is not muted and try again.',
    legendOpen: 'OPEN',
    legendClosed: 'CLOSED',
    legendPermanent: 'PERMANENT OPENING — CANNOT BE CLOSED',
    legendClick: 'CLICK A DOOR BAR TO TOGGLE IT',

    // game.js
    sessionUnavailable: 'Session unavailable',
    sessionUnavailableBody: (msg) => `${msg}. Sessions do not survive a backend restart.`,
    backToStart: 'Back to the start',
    nothingWaiting: 'NOTHING WAITING',
    openNotification: 'OPEN NOTIFICATION',
    waitingCount: (n) => `${n} WAITING`,
    penalties: 'PENALTIES',
    elapsed: 'ELAPSED',
    stationTime: 'STATION TIME',
    onShift: 'On shift',
    onShiftHint: 'Doors are yours. Messages arrive on the panel above.',
    debrief: 'Debrief — untimed',
    debriefHint: 'The shift is over. Nothing can fail now. Answer the last questions from memory.',
    confirmed: (text) => `CONFIRMED — ${text}`,

    // modal.js
    stationAlert: 'STATION ALERT',
    station: 'STATION',
    incomingQuery: 'INCOMING QUERY',
    radioAudioOnly: 'RADIO — AUDIO ONLY',
    text: 'TEXT',
    acknowledge: 'Acknowledge',
    audioUnavailable: 'AUDIO UNAVAILABLE — THIS SESSION IS VOID',
    transmissionEnded: (total) => `TRANSMISSION ENDED — ${total}`,
    openingChannel: 'OPENING CHANNEL',
    receiving: 'RECEIVING',
    receivingTotal: (total) => `RECEIVING — ${total}`,
    receivingProgress: (cur, total) => `RECEIVING — ${cur}s / ${total}`,
    audioBlocked: 'AUDIO BLOCKED — THIS SESSION IS VOID',
    outcomeCorrect: 'CORRECT',
    outcomeWrong: 'WRONG',
    outcomeDontKnow: 'NOT KNOWN',
    answerRequired: 'AN ANSWER IS REQUIRED. THE STATION IS STILL LIVE '
      + 'BEHIND THIS PANEL AND THE CLOCK IS STILL RUNNING.',

    // summary.js
    thread: 'Thread', obligation: 'Obligation', door: 'Door', askedBy: 'Asked by',
    asked: 'Asked', broke: 'Broke',
    nothingFailed: 'Nothing failed. Every obligation held.',
    debriefTag: 'DEBRIEF', onShiftTag: 'ON SHIFT',
    youSaid: 'You said: ',
    correctWas: 'Correct: ',
    noQuestionsAnswered: 'No questions were answered.',
    failedObligations: 'FAILED OBLIGATIONS',
    wrongOrUnknown: 'WRONG OR UNKNOWN',
    expiredUnread: 'EXPIRED UNREAD',
    whatBroke: 'What broke',
    questions: 'Questions',
    noThreadCost: 'No thread cost anything.',
    whatWasHappening: 'What was actually happening',
    cost: 'Cost',
  },
  fr: {
    // home.js
    stationHeader: (version) => `Station — ${version} — mode entraînement, rien n'est enregistré`,
    beginShift: 'Commencer une garde',
    participant: 'Participant',
    participantPlaceholder: 'nom ou code',
    scenario: 'Scénario',
    startShift: 'Commencer la garde',
    beforeYouStart: 'Avant de commencer',
    instructions: [
      '<strong>Cliquez sur une porte pour l\'ouvrir ou la fermer.</strong> Vert veut dire ouverte, rouge fermée. Essayez-les toutes maintenant — une fois la garde commencée, le chronomètre tourne et ne s\'arrête jamais.',
      '<strong>Deux endroits n\'ont pas de porte propre.</strong> Trouvez-les. Ils sont dessinés comme une brèche dans le mur plutôt qu\'une barre.',
      '<strong>Travaillez avec les fiches de secteur imprimées face à cette carte.</strong> Quelles portes délimitent un secteur est la seule chose que vous ne pouvez pas lire sur la station, et ce n\'est pas ce que la séance mesure.',
      '<strong>Vous recevez chaque message une seule fois.</strong> Pas d\'historique, pas de rediffusion, pas de pause. Les messages radio sont parlés et n\'ont pas de transcription. Stylo et papier sont autorisés.',
      'Appuyer sur <strong>Commencer la garde</strong> remet chaque porte dans sa position standard et active le son.',
    ],
    bankEmpty: '— la banque est vide —',
    someUnplayable: (n) => `${n} scénario(s) dans la banque, aucun jouable. `,
    openAdmin: 'Ouvrir l\'admin',
    toSeeWhy: ' pour voir pourquoi.',
    noScenariosYet: 'Aucun scénario pour l\'instant. ',
    generateOne: 'En générer un',
    scenarioOption: (s) => `${s.name} — ${Math.round(s.duration_seconds / 60)} min`,
    describe: (c) =>
      `${c.messages} messages, ${c.threads} fils, ${c.radio_messages} parlés. Station ${c.station_version}.`
      + (c.tunables_match ? '' : ' Validé avec des réglages de difficulté différents.'),
    soundFailed: (msg) => `Le son n'a pas pu démarrer (${msg}). `
      + 'Une séance sans son est nulle et non avenue, elle ne commencera donc pas. '
      + 'Vérifiez que le navigateur n\'est pas en sourdine et réessayez.',
    legendOpen: 'OUVERTE',
    legendClosed: 'FERMÉE',
    legendPermanent: 'OUVERTURE PERMANENTE — NE PEUT PAS ÊTRE FERMÉE',
    legendClick: 'CLIQUEZ SUR UNE BARRE DE PORTE POUR LA BASCULER',

    // game.js
    sessionUnavailable: 'Séance indisponible',
    sessionUnavailableBody: (msg) => `${msg}. Les séances ne survivent pas à un redémarrage du serveur.`,
    backToStart: 'Retour au début',
    nothingWaiting: 'RIEN EN ATTENTE',
    openNotification: 'OUVRIR LA NOTIFICATION',
    waitingCount: (n) => `${n} EN ATTENTE`,
    penalties: 'PÉNALITÉS',
    elapsed: 'ÉCOULÉ',
    stationTime: 'HEURE STATION',
    onShift: 'En garde',
    onShiftHint: 'Les portes sont à vous. Les messages arrivent sur le panneau ci-dessus.',
    debrief: 'Debrief — hors chronomètre',
    debriefHint: 'La garde est terminée. Plus rien ne peut échouer. Répondez aux dernières questions de mémoire.',
    confirmed: (text) => `CONFIRMÉ — ${text}`,

    // modal.js
    stationAlert: 'ALERTE STATION',
    station: 'STATION',
    incomingQuery: 'DEMANDE ENTRANTE',
    radioAudioOnly: 'RADIO — AUDIO SEUL',
    text: 'TEXTE',
    acknowledge: 'Accuser réception',
    audioUnavailable: 'AUDIO INDISPONIBLE — CETTE SÉANCE EST NULLE',
    transmissionEnded: (total) => `TRANSMISSION TERMINÉE — ${total}`,
    openingChannel: 'OUVERTURE DU CANAL',
    receiving: 'RÉCEPTION',
    receivingTotal: (total) => `RÉCEPTION — ${total}`,
    receivingProgress: (cur, total) => `RÉCEPTION — ${cur}s / ${total}`,
    audioBlocked: 'AUDIO BLOQUÉ — CETTE SÉANCE EST NULLE',
    outcomeCorrect: 'CORRECT',
    outcomeWrong: 'FAUX',
    outcomeDontKnow: 'NON SU',
    answerRequired: 'UNE RÉPONSE EST REQUISE. LA STATION EST TOUJOURS ACTIVE '
      + 'DERRIÈRE CE PANNEAU ET LE CHRONOMÈTRE CONTINUE DE TOURNER.',

    // summary.js
    thread: 'Fil', obligation: 'Obligation', door: 'Porte', askedBy: 'Demandé par',
    asked: 'Demandé', broke: 'Rompu',
    nothingFailed: 'Rien n\'a échoué. Chaque obligation a tenu.',
    debriefTag: 'DEBRIEF', onShiftTag: 'EN GARDE',
    youSaid: 'Vous avez dit : ',
    correctWas: 'Correct : ',
    noQuestionsAnswered: 'Aucune question n\'a été répondue.',
    failedObligations: 'OBLIGATIONS ÉCHOUÉES',
    wrongOrUnknown: 'FAUX OU INCONNU',
    expiredUnread: 'EXPIRÉ NON LU',
    whatBroke: 'Ce qui a échoué',
    questions: 'Questions',
    noThreadCost: 'Aucun fil n\'a rien coûté.',
    whatWasHappening: 'Ce qui se passait réellement',
    cost: 'Coût',
  },
};

export function strings(language) {
  return STRINGS[language] || STRINGS.en;
}
