import { describe, expect, it } from 'vitest';
import { Transcript } from './transcript.svelte';

/**
 * The rule these guard is one thing: what a reader sees has to be what has
 * arrived. An answer that streams in and is only visible after a page
 * reload is indistinguishable, from the outside, from an answer that was
 * never given.
 */

function delta(id: number, text: string) {
	return { type: 'message.delta', id, text };
}

describe('a turn being answered', () => {
	it('shows each fragment as it arrives, not only once it is reloaded', () => {
		const transcript = new Transcript();
		const answer = transcript.ask('What is in this library?');

		answer.apply({ type: 'message.started', id: 0, message_id: 'm1', conversation_id: 'c1' });

		// Read between events, which is what a render does. Reading only at
		// the end would pass even with the bug this guards: the staleness is
		// a value cached by the first read, so a test that never reads early
		// never has a stale value to be wrong about.
		answer.apply(delta(1, 'Two '));
		expect(transcript.turns[0].stream.text).toBe('Two ');

		answer.apply(delta(2, 'reports.'));

		// Read through the transcript rather than through the writer: the
		// writer's own copy was never the thing in doubt. This is what the
		// page renders, and it is what stayed empty when the turn was held
		// as an object and edited in place.
		expect(transcript.turns[0].stream.text).toBe('Two reports.');
		expect(transcript.turns[0].stream.conversationId).toBe('c1');
	});

	it('keeps the text an answer managed to write before it failed', () => {
		const transcript = new Transcript();
		const answer = transcript.ask('And the second one?');

		answer.apply(delta(0, 'It is '));
		answer.fail('connection_lost', 'The connection closed before the answer finished.');

		expect(transcript.turns[0].stream.text).toBe('It is ');
		expect(transcript.turns[0].stream.error?.code).toBe('connection_lost');
		expect(transcript.turns[0].stream.done).toBe(true);
	});

	it('writes into its own turn while earlier ones stand', () => {
		const transcript = new Transcript();
		const first = transcript.ask('First?');
		first.apply(delta(0, 'One.'));
		const second = transcript.ask('Second?');
		second.apply(delta(0, 'Two.'));

		expect(transcript.turns.map((turn) => turn.stream.text)).toEqual(['One.', 'Two.']);
		expect(transcript.turns.map((turn) => turn.question)).toEqual(['First?', 'Second?']);
	});

	it('does not write a late event into the thread that replaced it', () => {
		const transcript = new Transcript();
		const abandoned = transcript.ask('Asked, then left behind');
		transcript.clear();
		transcript.ask('A different thread');

		abandoned.apply(delta(0, 'text from the conversation that was closed'));

		expect(transcript.turns).toHaveLength(1);
		expect(transcript.turns[0].question).toBe('A different thread');
		expect(transcript.turns[0].stream.text).toBe('');
	});
});
