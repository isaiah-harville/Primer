import { describe, expect, it } from 'vitest';
import { CITATION_PREFIX, citationFrom, linkCitations } from './citations';

describe('linkCitations', () => {
	it('turns a marker into a link to the passage it names', () => {
		expect(linkCitations('The budget rose [1].', 1)).toBe(
			`The budget rose [[1]](${CITATION_PREFIX}1).`,
		);
	});

	it('leaves a marker numbered past the citations that arrived', () => {
		// A model that cites a fourth source when three were retrieved has
		// said something wrong. A link leading nowhere would dress that up
		// as something the interface can honour.
		expect(linkCitations('Claimed in [4].', 3)).toBe('Claimed in [4].');
	});

	it('leaves code alone', () => {
		const text = 'Read `rows[1]` first.\n\n```\nvalues[2]\n```\n';
		expect(linkCitations(text, 3)).toBe(text);
	});

	it('leaves a link the model wrote itself', () => {
		const text = 'See [1](https://example.edu/paper).';
		expect(linkCitations(text, 3)).toBe(text);
	});

	it('rewrites every marker in a sentence', () => {
		expect(linkCitations('Both [1] and [2] say so.', 2)).toBe(
			`Both [[1]](${CITATION_PREFIX}1) and [[2]](${CITATION_PREFIX}2) say so.`,
		);
	});

	it('changes nothing when the answer cited nothing', () => {
		expect(linkCitations('An uncited answer [1].', 0)).toBe('An uncited answer [1].');
	});

	it('is unchanged by being run a second time', () => {
		// The answer is rewritten on every render while it streams, so a
		// pass over text this has already touched has to be a no-op.
		const once = linkCitations('The budget rose [1].', 1);
		expect(linkCitations(once, 1)).toBe(once);
	});
});

describe('citationFrom', () => {
	it('reads the position out of a marker link', () => {
		expect(citationFrom(`${CITATION_PREFIX}3`)).toBe(3);
	});

	it('ignores a link that is not a marker', () => {
		// A model's own links have to keep behaving like links.
		expect(citationFrom('https://example.edu/paper')).toBeNull();
		expect(citationFrom('#introduction')).toBeNull();
		expect(citationFrom(null)).toBeNull();
	});
});
