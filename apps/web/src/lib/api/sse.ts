import type { Citation, MessageSummary } from './types';

/**
 * Reading Primer's event stream.
 *
 * Only known event types are acted on. An unrecognised one is skipped rather
 * than guessed at: a future server that adds an event must not make an older
 * browser render something it does not understand.
 */

export interface StreamState {
	messageId: string | null;
	conversationId: string | null;
	/** Accumulated text, in arrival order. */
	text: string;
	citations: Citation[];
	message: MessageSummary | null;
	error: { code: string; detail: string | null } | null;
	/** The highest event id seen, for resuming. */
	lastEventId: number;
	done: boolean;
}

export function emptyStream(): StreamState {
	return {
		messageId: null,
		conversationId: null,
		text: '',
		citations: [],
		message: null,
		error: null,
		lastEventId: -1,
		done: false,
	};
}

interface RawEvent {
	type?: string;
	id?: number;
	[key: string]: unknown;
}

/**
 * Fold one event into the running state.
 *
 * Out-of-order and repeated events are dropped by id. A reconnect replays
 * from a point the client already saw, and applying those deltas twice
 * would duplicate text in the middle of an answer.
 */
export function reduce(state: StreamState, event: RawEvent): StreamState {
	const id = typeof event.id === 'number' ? event.id : -1;
	if (id <= state.lastEventId) return state;
	const next: StreamState = { ...state, lastEventId: id };

	switch (event.type) {
		case 'message.started':
			next.messageId = String(event.message_id);
			next.conversationId = String(event.conversation_id);
			return next;
		case 'message.delta':
			// Concatenated exactly as received: the space between two words
			// routinely arrives as one fragment's trailing character.
			next.text = state.text + String(event.text ?? '');
			return next;
		case 'citation':
			next.citations = [...state.citations, event.citation as Citation];
			return next;
		case 'message.completed':
			next.message = event.message as MessageSummary;
			next.text = next.message.content;
			next.citations = next.message.citations;
			next.done = true;
			return next;
		case 'error':
			// The accumulated text is kept. A half-written answer is evidence
			// of what went wrong, and blanking it loses the only thing the
			// user can see about it.
			next.error = { code: String(event.code), detail: (event.detail as string) ?? null };
			next.done = true;
			return next;
		case 'heartbeat':
			return next;
		default:
			return next;
	}
}

/**
 * Split an SSE byte stream into events.
 *
 * Frames are separated by a blank line and can arrive split across chunks,
 * so a partial frame is held back rather than parsed as a whole one.
 */
export async function* parseEvents(body: ReadableStream<Uint8Array>): AsyncGenerator<RawEvent> {
	const reader = body.getReader();
	const decoder = new TextDecoder();
	let buffer = '';

	while (true) {
		const { done, value } = await reader.read();
		if (done) break;
		buffer += decoder.decode(value, { stream: true });

		let boundary = buffer.indexOf('\n\n');
		while (boundary !== -1) {
			const frame = buffer.slice(0, boundary);
			buffer = buffer.slice(boundary + 2);
			const parsed = parseFrame(frame);
			if (parsed) yield parsed;
			boundary = buffer.indexOf('\n\n');
		}
	}
}

export function parseFrame(frame: string): RawEvent | null {
	const data = frame
		.split('\n')
		.filter((line) => line.startsWith('data: '))
		.map((line) => line.slice('data: '.length))
		.join('\n');
	if (!data) return null;
	try {
		return JSON.parse(data) as RawEvent;
	} catch {
		// A truncated or malformed frame is skipped rather than aborting the
		// stream: the rest of the answer is still worth showing.
		return null;
	}
}
