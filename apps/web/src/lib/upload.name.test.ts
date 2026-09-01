import { describe, expect, it } from 'vitest';
import { libraryNameFor } from './upload';

/**
 * Naming a library after the file that caused it to exist.
 *
 * The name is what the user reads when asked whether to keep the library, so
 * it has to say something about the contents. It is a starting point rather
 * than a decision - they can rename it - but a bad starting point makes the
 * question unanswerable.
 */
describe('libraryNameFor', () => {
	it('reads a filename as words', () => {
		expect(libraryNameFor('dense-passage-retrieval.pdf')).toBe('Dense passage retrieval');
		expect(libraryNameFor('quarterly_report_2026.docx')).toBe('Quarterly report 2026');
	});

	it('splits words that were only separated by capitals', () => {
		expect(libraryNameFor('AnnualReport.pdf')).toBe('Annual Report');
	});

	it('keeps the whole name when there is no extension', () => {
		expect(libraryNameFor('README')).toBe('README');
	});

	// A dotfile's leading dot is not an extension, and treating it as one
	// would leave nothing at all.
	it('does not mistake a leading dot for an extension', () => {
		expect(libraryNameFor('.gitignore')).toBe('Gitignore');
	});

	it('collapses runs of separators rather than leaving gaps', () => {
		expect(libraryNameFor('notes -- draft__v2.md')).toBe('Notes draft v2');
	});

	// Control rejects a name over its limit, and a rejected upload here would
	// look like the file was the problem.
	it('stays within the length Control accepts', () => {
		const name = libraryNameFor(`${'word '.repeat(60)}.pdf`);
		expect(name.length).toBeLessThanOrEqual(120);
		expect(name.endsWith(' ')).toBe(false);
	});

	it('falls back to something usable when nothing is left', () => {
		expect(libraryNameFor('___.pdf')).toBe('New library');
		expect(libraryNameFor('')).toBe('New library');
	});
});
