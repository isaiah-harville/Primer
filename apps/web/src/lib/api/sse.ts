import { createParser } from 'eventsource-parser';
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
	/**
	 * What the model worked through, for one that thinks aloud.
	 *
	 * Null until a reasoning event arrives, so a model that does not think
	 * aloud is distinguishable from one that does and has not started. The
	 * interface shows nothing at all for the former.
	 */
	reasoning: string | null;
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
		reasoning: null,
		citations: [],
		message: null,
		error: null,
		lastEventId: -1,
		done: false,
	};
}

export interface RawEvent {
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
		case 'reasoning.delta':
			// Its own channel, never folded into the answer: the answer is
			// what a reader copies, exports, and cites.
			next.reasoning = (state.reasoning ?? '') + String(event.text ?? '');
			return next;
		case 'citation':
			next.citations = [...state.citations, event.citation as Citation];
			return next;
		case 'message.completed':
			next.message = event.message as MessageSummary;
			next.text = next.message.content;
			// The stored value wins, so a reopened thread and a freshly
			// streamed one show the same thing.
			next.reasoning = next.message.reasoning ?? next.reasoning;
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
 * The framing is `eventsource-parser`'s rather than ours. What we had
 * handled the shape our own server happens to send and only that: a frame
 * separator of exactly `\n\n`, and a `data:` prefix with exactly one space
 * after the colon. Both are narrower than the specification. The space is
 * optional, so a compliant `data:{"id":1}` was **silently dropped** - no
 * error, just an event that never arrived - and a `\r\n\r\n` separator is
 * not found by a search for `\n\n` at all, so a stream using it would
 * hang rather than yield.
 *
 * Nothing was broken in practice, because Primer's own `sse.py` writes the
 * one shape the old parser understood. That is the problem with it: it
 * worked by agreement with a single sender rather than by following the
 * protocol, and anything between the two - an edge proxy, a future
 * endpoint - only had to be correct to break it.
 */
export async function* parseEvents(body: ReadableStream<Uint8Array>): AsyncGenerator<RawEvent> {
	const ready: RawEvent[] = [];
	const parser = createParser({
		onEvent: (message) => {
			const event = decode(message.data);
			if (event) ready.push(event);
		},
		// A malformed frame is skipped rather than aborting the stream: the
		// rest of the answer is still worth showing. `terminate` would throw
		// away a whole answer over one bad line.
		onError: () => {},
	});

	// A reader rather than `for await` over the stream. Async iteration of a
	// ReadableStream is still missing from Chrome and Safari, so iterating
	// the piped stream directly would work in Node, pass in tests, and fail
	// in most browsers.
	const reader = body.getReader();
	const decoder = new TextDecoder();
	while (true) {
		const { done, value } = await reader.read();
		if (done) return;
		// `stream: true`, because a multi-byte character can be split across
		// two chunks and decoding each alone would corrupt it.
		parser.feed(decoder.decode(value, { stream: true }));
		while (ready.length > 0) yield ready.shift() as RawEvent;
	}
}

/**
 * One event's JSON payload, or null when it is not usable.
 *
 * Primer puts everything in `data` as JSON, including the id it dedupes on
 * - the SSE `id:` field carries the same number, but as text, and reading
 * one of the two rather than both keeps a single source of truth.
 */
export function decode(data: string): RawEvent | null {
	if (!data) return null;
	try {
		return JSON.parse(data) as RawEvent;
	} catch {
		// A truncated or malformed payload is skipped rather than aborting
		// the stream: the rest of the answer is still worth showing.
		return null;
	}
}
