import type { VoiceAction, VoiceIntent } from './voiceControl'

export type VoiceInputStage =
  | 'IDLE'
  | 'RECORDING'
  | 'TRANSCRIBING'
  | 'READY_TO_PARSE'
  | 'PARSING'
  | 'CANDIDATE'
  | 'NEEDS_CLARIFICATION'
  | 'UNSUPPORTED'
  | 'ERROR'

export type VoiceParseStatus = 'CANDIDATE' | 'NEEDS_CLARIFICATION' | 'UNSUPPORTED' | 'NOT_ACTIONABLE'
export type VoiceParseReason =
  | 'AMBIGUOUS_ACTION'
  | 'NEGATED_ACTION'
  | 'NO_SUPPORTED_ACTION'
  | 'UNSUPPORTED_CAPABILITY'
  | 'UNSUPPORTED_TARGETING'

export interface VoiceAudioInput {
  audio: Blob
  locale: string
  requestId: string
}

export interface VoiceTranscript {
  requestId: string
  text: string
  provider: string
  model: string
}

export interface VoiceParseRequest {
  requestId: string
  text: string
  locale: string
  allowedActions: VoiceAction[]
  availableDeviceCodes: string[]
}

export interface VoiceIntentCandidate {
  status: 'CANDIDATE'
  requestId: string
  intent: VoiceIntent
  action: VoiceAction
  normalizedText: string
  confidence: number | null
  provider: string
  model: string
}

export interface VoiceIntentNotReady {
  status: Exclude<VoiceParseStatus, 'CANDIDATE'>
  requestId: string
  reason: VoiceParseReason
  message: string
  normalizedText: string
  provider: string
  model: string
}

export type VoiceParseResult = VoiceIntentCandidate | VoiceIntentNotReady

/** Provider-neutral seam. Implementations belong in the backend integration layer. */
export interface VoiceIntelligenceAdapter {
  readonly name: string
  readonly mode: 'MOCK' | 'BACKEND'
  transcribe(input: VoiceAudioInput): Promise<VoiceTranscript>
  parse(input: VoiceParseRequest): Promise<VoiceParseResult>
}
