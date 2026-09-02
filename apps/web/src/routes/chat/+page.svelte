<script lang="ts">
	import {
		Alert,
		Button,
		Conversation,
		Markdown,
		Message,
		PromptComposer,
		Spinner
	} from '@sivir-ui/svelte';
	import { invalidateAll } from '$app/navigation';
	import CitationPanel from '$lib/components/CitationPanel.svelte';
	import LibraryLink from '$lib/components/LibraryLink.svelte';
	import ModelPicker from '$lib/components/ModelPicker.svelte';
	import ResponseActions from '$lib/components/ResponseActions.svelte';
	import { emptyStream, parseEvents, reduce, type StreamState } from '$lib/api/sse';
	import type { MessageSummary } from '$lib/api/types';
	import { rejectionFor } from '$lib/upload';
	import { discardLibrary, uploadDocument } from '$lib/upload-client';
	import type { PageData } from './$types';

	let { data }: { data: PageData } = $props();

	// Empty means no library, which is a usable state rather than a missing
	// one: the model answers on its own. Nothing is chosen by default,
	// because silently attaching the first library would make an answer look
	// grounded in something the user never picked.
	let libraryId = $state('');
	// Empty means the deployment's default, which is also what a request that
	// names no model gets. Not defaulted to a name here: the server decides
	// what its default is, and copying that choice into the client would let
	// the two disagree.
	let model = $state('');
	let question = $state('');
	let turns = $state<{ question: string; stream: StreamState }[]>([]);
	// Set by the first answer and sent with every question after it. Without
	// it each question opened its own conversation, so the model never saw
	// the turn before - and a follow-up like "and the second one?" had
	// nothing to resolve against.
	let conversationId = $state<string | null>(null);
	let streaming = $state(false);
	let sourcesOpen = $state(false);
	let sourcesFor = $state<StreamState | null>(null);

	// The library is fixed when the conversation opens: follow-up questions
	// carry only the conversation, so changing it now would change nothing.
	let started = $derived(conversationId !== null);
	let dragging = $state(false);
	let linkedName = $derived(data.libraries.find((library) => library.id === libraryId)?.name);
	let uploading = $state<string[]>([]);
	let uploadError = $state('');
	let announcement = $state('');
	//: Set only when dropping a file created the library holding it, which is
	//: the one case where the user should be asked whether to keep it.
	let offered = $state<{ id: string; name: string; documents: number } | null>(null);

	async function accept(files: File[]) {
		uploadError = '';
		// A file dropped here would land in a library this conversation
		// cannot be asked about, and the upload would look like it worked.
		if (started && !libraryId) {
			uploadError =
				'This conversation was started without a library. Start a new chat to ask about a file.';
			announcement = uploadError;
			return;
		}
		for (const file of files) {
			const rejection = rejectionFor(file, data.capabilities);
			if (rejection) {
				uploadError = rejection.message;
				announcement = rejection.message;
				continue;
			}

			uploading = [...uploading, file.name];
			announcement = `Uploading ${file.name}.`;
			try {
				const result = await uploadDocument(file, libraryId || undefined);
				// Linking it is the point: a file dropped into a conversation
				// was dropped there to be asked about.
				libraryId = result.libraryId;
				if (result.created && result.libraryName) {
					offered = { id: result.libraryId, name: result.libraryName, documents: 1 };
				} else if (offered && offered.id === result.libraryId) {
					offered = { ...offered, documents: offered.documents + 1 };
				}
				announcement = `${file.name} added to ${result.libraryName ?? 'the library'}.`;
			} catch (error) {
				uploadError = error instanceof Error ? error.message : `${file.name} could not be uploaded.`;
				announcement = uploadError;
			} finally {
				uploading = uploading.filter((name) => name !== file.name);
			}
		}
		// The sidebar counts documents, and it is on this page too.
		await invalidateAll();
	}

	async function discard() {
		if (!offered) return;
		const library = offered;
		offered = null;
		libraryId = '';
		try {
			await discardLibrary(library.id);
		} catch (error) {
			uploadError = error instanceof Error ? error.message : 'That library could not be removed.';
		}
		await invalidateAll();
	}

	async function ask() {
		const asked = question.trim();
		if (!asked || streaming) return;

		question = '';
		streaming = true;
		const turn = { question: asked, stream: emptyStream() };
		turns = [...turns, turn];

		try {
			const response = await fetch('/chat/ask', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				// Omitted rather than sent empty when nothing is linked: the
				// absence of a library is what asks for an uncited answer.
				// Fields are omitted rather than sent empty: no library asks for
				// an uncited answer, and no model asks for the default.
				body: JSON.stringify({
					message: asked,
					...(conversationId ? { conversation_id: conversationId } : {}),
					...(libraryId ? { library_id: libraryId } : {}),
					...(model ? { model } : {})
				})
			});
			if (!response.ok || !response.body) throw new Error('The server refused the question.');

			for await (const event of parseEvents(response.body)) {
				// Reassigning the array is what makes Svelte see the change;
				// the state object itself is replaced by the reducer.
				turn.stream = reduce(turn.stream, event);
				turns = [...turns];
			}
			// Taken from the answer rather than assumed, so the next question
			// continues the conversation the server actually opened.
			conversationId = turn.stream.conversationId ?? conversationId;
		} catch {
			turn.stream = {
				...turn.stream,
				error: { code: 'connection_lost', detail: 'The connection closed before the answer finished.' },
				done: true
			};
			turns = [...turns];
		} finally {
			streaming = false;
		}
	}

	// The library and the model are kept: starting over is usually asking
	// something else about the same documents, not changing what is at hand.
	function startOver() {
		turns = [];
		conversationId = null;
		question = '';
		sourcesFor = null;
		sourcesOpen = false;
		uploadError = '';
		announcement = 'Started a new chat.';
	}

	function completed(stream: StreamState): MessageSummary | null {
		if (stream.message) return stream.message;
		// A failed stream still has an answer worth copying: the text it
		// managed to write before it stopped.
		if (!stream.error || !stream.messageId) return null;
		return {
			id: stream.messageId,
			conversation_id: stream.conversationId ?? '',
			role: 'assistant',
			state: 'failed',
			content: stream.text,
			citations: stream.citations,
			error_code: stream.error.code,
			created_at: new Date().toISOString()
		};
	}
</script>

<!--
  The chat fills the height it is given, so the composer sits at the bottom
  of the frame rather than under the conversation wherever that happens to
  end.
-->
<div class="flex h-full flex-col">
	<div class="flex shrink-0 items-center justify-between gap-4">
		<h1 class="text-xl font-semibold tracking-[-0.02em]">Chat</h1>
		<!--
		  The way back to a blank page, and the only way to change the library
		  a conversation is answered from. Absent until there is something to
		  leave behind.
		-->
		{#if turns.length > 0}
			<Button size="sm" variant="ghost" onclick={startOver} disabled={streaming}>New chat</Button>
		{/if}
	</div>

<!--
  Constrained here rather than in the frame. Answers are prose, and prose set
  the full width of a desktop window is unreadable - but the frame around it
  holds tables that need every pixel.
-->
<!--
  The whole conversation is the drop target, not a separate upload control.
  Dropping a file into a chat is how people expect to add something to what
  they are talking about, and a dropzone beside it would be a second place to
  do the same thing.
-->
<div
	class="relative mx-auto mt-6 flex min-h-0 w-full max-w-3xl flex-1 flex-col"
	ondragover={(event) => {
		event.preventDefault();
		dragging = true;
	}}
	ondragleave={(event) => {
		// Only when the pointer leaves the region itself: moving between
		// children fires dragleave constantly and would flicker the overlay.
		if (!event.currentTarget.contains(event.relatedTarget as Node)) dragging = false;
	}}
	ondrop={(event) => {
		event.preventDefault();
		dragging = false;
		void accept([...(event.dataTransfer?.files ?? [])]);
	}}
	role="presentation"
>
	{#if dragging}
		<!--
		  Named rather than a bare highlight, because where the file lands is
		  the thing in question: an existing library, or a new one.
		-->
		<div
			class="pointer-events-none absolute inset-0 z-20 flex items-center justify-center
				rounded-lg border-2 border-dashed border-primary bg-background/85 text-sm font-medium"
		>
			{linkedName
				? `Add to ${linkedName}`
				: 'Drop to start a library from this file'}
		</div>
	{/if}

	<Conversation.Root class="flex-1">
		<Conversation.Content>
			{#if turns.length === 0}
				<Conversation.Empty>
					{#if libraryId}
						Ask a question about this library. Every answer cites the passages it used.
					{:else}
						Ask anything. Link a library below to have answers drawn from your own
						documents and cited.
					{/if}
				</Conversation.Empty>
			{/if}

			{#each turns as turn, index (index)}
				<Message.Root from="user">
					<Message.Content>{turn.question}</Message.Content>
				</Message.Root>

				<Message.Root from="assistant" status={turn.stream.done ? 'idle' : 'streaming'}>
					<Message.Content>
						<!--
						  Rendered as Markdown, since models write it. The text
						  is the model's, so it is rendered rather than
						  interpreted: nothing here acts on it.
						-->
						<Markdown content={turn.stream.text} />
					</Message.Content>

					{#if turn.stream.error}
						<Alert.Root variant="error" class="mt-2">
							<Alert.Description>
								{turn.stream.error.detail ?? 'The answer stopped before it finished.'}
							</Alert.Description>
						</Alert.Root>
					{/if}

					{#if turn.stream.done}
						{@const message = completed(turn.stream)}
						{#if message}
							<Message.Actions>
								<ResponseActions
									{message}
									onshowsources={() => {
										sourcesFor = turn.stream;
										sourcesOpen = true;
									}}
								/>
							</Message.Actions>
						{/if}
					{/if}
				</Message.Root>
			{/each}
		</Conversation.Content>
		<Conversation.ScrollButton />
	</Conversation.Root>

	<PromptComposer.Root
		bind:value={question}
		status={streaming ? 'submitting' : 'idle'}
		onSubmit={ask}
		class="mt-4"
	>
		<PromptComposer.Input
			placeholder={libraryId ? 'Ask about this library…' : 'Ask anything…'}
			aria-label="Your question"
		/>
		<PromptComposer.Toolbar>
			<PromptComposer.Actions>
				<PromptComposer.Submit />
			</PromptComposer.Actions>
		</PromptComposer.Toolbar>
	</PromptComposer.Root>

	<!--
	  Below the composer, because whether this question is answered from your
	  documents belongs with asking it rather than with the page around it.
	-->
	<div class="mt-2 flex flex-wrap items-center justify-between gap-3">
		<div class="flex flex-wrap items-center gap-2">
			<LibraryLink libraries={data.libraries} bind:value={libraryId} locked={started} />
			<ModelPicker models={data.models} bind:value={model} />
			{#each uploading as name (name)}
				<span class="flex items-center gap-2 text-xs text-muted-foreground">
					<Spinner size={12} aria-hidden="true" />
					{name}
				</span>
			{/each}
		</div>

		{#if !libraryId}
			<p class="text-xs text-muted-foreground">Answers will not be cited.</p>
		{/if}
	</div>

	<!--
	  Uploads happen without the user reading this corner of the page, so they
	  are announced politely rather than left to be noticed.
	-->
	<p class="sr-only" aria-live="polite">{announcement}</p>

	{#if uploadError}
		<Alert.Root variant="error" class="mt-3">
			<Alert.Description>{uploadError}</Alert.Description>
		</Alert.Root>
	{/if}

	{#if offered}
		<!--
		  Asked, not assumed. Dropping a file into a conversation with nowhere
		  to put it had to create somewhere, and a library the user never
		  chose should not quietly become permanent. Keeping is the default
		  action because the document is already in it and already searchable.
		-->
		<div
			class="mt-3 flex flex-wrap items-center gap-3 rounded-lg border border-border
				bg-card p-3 text-sm shadow-[var(--elevation-1)]"
		>
			<span class="min-w-0 flex-1">
				Started a library called
				<strong class="font-medium">{offered.name}</strong>
				to hold
				{offered.documents === 1 ? 'this file' : `these ${offered.documents} files`}. Keep it?
			</span>
			<div class="flex items-center gap-2">
				<Button size="sm" onclick={() => (offered = null)}>Keep</Button>
				<Button size="sm" variant="ghost" onclick={discard}>Discard</Button>
			</div>
		</div>
	{/if}
</div>

</div>

{#if sourcesFor}
	<CitationPanel citations={sourcesFor.citations} bind:open={sourcesOpen} />
{/if}
