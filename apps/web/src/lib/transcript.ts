import { emptyStream, type StreamState } from '$lib/api/sse';
import type { MessageSummary } from '$lib/api/types';

/**
 * Reading a stored conversation back onto the screen.
 *
 * What is stored is a flat sequence of messages; what is shown is a turn -
 * a question with the answer to it. The pairing happens here rather than in
 * the page so that the awkward cases have somewhere to be tested.
 */

export interface Turn {
	question: string;
	stream: StreamState;
}

function answered(message: MessageSummary): StreamState {
	return {
		...emptyStream(),
		messageId: message.id,
		conversationId: message.conversation_id,
		text: message.content,
		citations: message.citations,
		message,
		// A failed answer is still failed when it is read back, and the half
		// it managed to write is still shown. Storing that half was the whole
		// point of storing it.
		error:
			message.state === 'failed'
				? { code: message.error_code ?? 'generation_failed', detail: null }
				: null,
		done: true,
	};
}

/**
 * Turns, in the order they were written.
 *
 * An answer with no question before it gets an empty one rather than being
 * dropped. It is a real thing that was said, and hiding it would make the
 * transcript disagree with what is stored - which is the one thing a
 * transcript must not do.
 */
export function turnsFrom(messages: MessageSummary[]): Turn[] {
	const turns: Turn[] = [];
	for (const message of messages) {
		if (message.role === 'user') {
			turns.push({ question: message.content, stream: { ...emptyStream(), done: true } });
			continue;
		}
		const last = turns.at(-1);
		// Only a turn still waiting for its answer takes this one. Two
		// answers in a row are two turns, not one answer overwriting another.
		if (last && last.stream.message === null && last.stream.error === null) {
			last.stream = answered(message);
		} else {
			turns.push({ question: '', stream: answered(message) });
		}
	}
	return turns;
}
