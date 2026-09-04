/**
 * The thread being written but not yet stored.
 *
 * A conversation is created when the first question is asked, so until an
 * answer comes back there is nothing in the sidebar to say where you are.
 * The thread then appeared in the timeline as the answer landed, which read
 * as the window jumping rather than as the thread being saved.
 *
 * So the timeline shows it from the moment it starts, from here rather than
 * from storage. Creating an empty conversation server-side would do the same
 * job and leave a row behind every time somebody opened a new chat and
 * thought better of it.
 *
 * Client-side and deliberately not persisted: it describes what is on this
 * screen right now, and a reload legitimately has none.
 */

class Draft {
	/** What the unsaved thread is called, or null when there is not one. */
	title = $state<string | null>(null);

	/**
	 * Start showing one.
	 *
	 * Named from the question, like a stored conversation, so the entry does
	 * not change its wording when it is saved a moment later.
	 */
	begin(question: string) {
		this.title = question.trim() || 'New chat';
	}

	/** It has been stored, so the real entry takes over. */
	settle() {
		this.title = null;
	}
}

export const draft = new Draft();
