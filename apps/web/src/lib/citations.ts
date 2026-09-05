/**
 * Making the markers in an answer lead to the passage they name.
 *
 * A model writes its citations as `[1]`, `[2]` in the prose. Those are the
 * reader's only handle on where a claim came from, and until now they were
 * text: you read `[3]`, opened the sources panel, and counted. The markers
 * are rewritten into links so that the handle is the thing you click.
 *
 * Rewriting the Markdown rather than reaching into the rendered DOM is
 * deliberate. The answer is already rendered by a Markdown component that
 * takes no hook of its own, and editing the nodes it produced would mean
 * editing DOM that Svelte owns and rewrites. A link is something the
 * renderer already understands.
 *
 * Nothing here trusts the model's text: the marker is matched, its number
 * is checked against the citations that actually arrived, and the href is
 * one this module constructs. The text between markers is untouched.
 */

/** The scheme-less href a citation marker is given. */
export const CITATION_PREFIX = '#citation-';

//: Code, fenced or inline. A `[1]` inside a code sample is part of the
//: sample - most often an array index - and turning it into a citation
//: would put a link in the middle of something a reader is going to copy.
const CODE = /(```[\s\S]*?```|~~~[\s\S]*?~~~|`[^`\n]*`)/g;

//: A bare `[n]`. Not one already followed by `(`, which is a Markdown link
//: the model wrote itself, and not one already inside another bracket,
//: which is what this rewrite produces - so running it twice is harmless.
const MARKER = /(?<![[\\])\[(\d{1,3})\](?!\()/g;

/**
 * Turn `[n]` into a link, for every marker naming a citation that exists.
 *
 * A marker numbered past the end is left as text. A model that cites a
 * fourth source when three were retrieved has said something wrong, and a
 * link leading nowhere would dress that up as something the interface can
 * honour.
 */
export function linkCitations(text: string, count: number): string {
	if (count <= 0 || !text) return text;
	return text
		.split(CODE)
		.map((segment, index) =>
			// `split` on a capturing group alternates: the odd positions are
			// the delimiters themselves, which here are the code spans.
			index % 2 === 1
				? segment
				: segment.replace(MARKER, (marker, digits: string) => {
						const position = Number(digits);
						if (position < 1 || position > count) return marker;
						return `[[${position}]](${CITATION_PREFIX}${position})`;
					}),
		)
		.join('');
}

/**
 * The citation a link points at, or null for any other link.
 *
 * Used to tell a marker apart from a link the model wrote into its answer,
 * which must keep behaving like a link.
 */
export function citationFrom(href: string | null | undefined): number | null {
	if (!href?.startsWith(CITATION_PREFIX)) return null;
	const digits = href.slice(CITATION_PREFIX.length);
	if (!/^\d{1,3}$/.test(digits)) return null;
	const position = Number(digits);
	return position >= 1 ? position : null;
}
