import { describe, expect, it } from 'vitest';
import { emptyStream, parseFrame, reduce } from './sse';

describe('SSE reduction', () => {
	it('coalesces deltas in arrival order', () => {
		let state = emptyStream();
		state = reduce(state, { type: 'message.delta', id: 0, text: 'Grounded ' });
		state = reduce(state, { type: 'message.delta', id: 1, text: 'answer.' });

		// The space between words routinely arrives as a fragment's trailing
		// character; joining without care welds them together.
		expect(state.text).toBe('Grounded answer.');
	});

	it('ignores an event it has already seen', () => {
		// A reconnect replays from a point the client saw; applying those
		// deltas twice duplicates text mid-answer.
		let state = emptyStream();
		state = reduce(state, { type: 'message.delta', id: 0, text: 'once' });
		state = reduce(state, { type: 'message.delta', id: 0, text: 'once' });

		expect(state.text).toBe('once');
	});

	it('keeps the text it accumulated when the stream errors', () => {
		let state = emptyStream();
		state = reduce(state, { type: 'message.delta', id: 0, text: 'Partial ' });
		state = reduce(state, { type: 'error', id: 1, code: 'generation_failed', detail: null });

		expect(state.text).toBe('Partial ');
		expect(state.error?.code).toBe('generation_failed');
		expect(state.done).toBe(true);
	});

	it('collects citations before any text arrives', () => {
		let state = emptyStream();
		state = reduce(state, {
			type: 'citation',
			id: 0,
			citation: {
				document_id: 'd',
				document_version_id: 'v',
				chunk_id: 'c',
				locator: null,
				excerpt: null,
			},
		});

		expect(state.citations).toHaveLength(1);
		expect(state.text).toBe('');
	});

	it('skips an event type it does not know', () => {
		// A newer server must not make an older browser render nonsense.
		let state = emptyStream();
		state = reduce(state, { type: 'tool.requested', id: 0 });

		expect(state.done).toBe(false);
		expect(state.text).toBe('');
		expect(state.lastEventId).toBe(0);
	});

	it('takes the completed message as final', () => {
		let state = emptyStream();
		state = reduce(state, { type: 'message.delta', id: 0, text: 'draft' });
		state = reduce(state, {
			type: 'message.completed',
			id: 1,
			message: {
				id: 'm',
				conversation_id: 'c',
				role: 'assistant',
				state: 'completed',
				content: 'the stored answer',
				citations: [],
				error_code: null,
				created_at: '2026-08-31T00:00:00Z',
			},
		});

		expect(state.text).toBe('the stored answer');
		expect(state.done).toBe(true);
	});

	it('reads a framed event', () => {
		const parsed = parseFrame('id: 3\nevent: message.delta\ndata: {"id":3,"text":"hi"}');
		expect(parsed).toEqual({ id: 3, text: 'hi' });
	});

	it('skips a malformed frame rather than aborting', () => {
		// The rest of the answer is still worth showing.
		expect(parseFrame('id: 3\ndata: {"id":3,')).toBeNull();
		expect(parseFrame(': keepalive')).toBeNull();
	});
});
