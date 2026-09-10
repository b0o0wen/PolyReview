/**
 * @polyreview/dsh-headless-resume — headless runner with session resume.
 *
 * Drop-in replacement for @deepseek-ai/dsh-headless that adds --resume support.
 * Based on the original headless runner source (MIT, DeepSeek AI), with:
 *   - --resume <session-uuid>: load a persisted session and continue it
 *   - session UUID printed to stderr after completion (for next resume)
 *
 * Usage:
 *   New session:   dsh --profile headless-resume "<task>"
 *   Resume:        dsh --profile headless-resume --resume <uuid> "<task>"
 *
 * Install:
 *   dsh --profile headless-resume --from-default-profile headless
 *   dsh plugin --profile headless-resume add @polyreview/dsh-headless-resume
 *
 * @module @polyreview/dsh-headless-resume
 */

import { randomUUID } from "node:crypto";
import z from "@deepseek-ai/schemastery";
import { brandString } from "@deepseek-ai/dsh-brand";
import { installModelSelection } from "@deepseek-ai/dsh-agent";
import { createUserMessage } from "@deepseek-ai/dsh-llm";
import { assertNever } from "@deepseek-ai/dsh-util-values";
import { SessionSeq } from "@deepseek-ai/dsh-session";

/** Stable Cordis plugin name. */
const name = "headless-resume-runner";

/** Core services required before the one-shot turn can start. */
const inject = [
	"agentDefaultModel",
	"agents",
	"sessions"
];

/** Accept task + optional resume session UUID. */
const Config = z.object({
	task: z.string().required(),
	resume: z.string().optional()
});

const internals = {
	stdout: process.stdout,
	stderr: process.stderr
};

/** Extract the session UUID from a brandString like "session-<uuid>" or a raw UUID. */
function sessionUuid(sessionId) {
	return String(sessionId).replace(/^session-/, "");
}

/** Summarize last assistant text and turn outcome (same as original headless). */
function summarize(session, firstSeq) {
	let started = false;
	let text = "";
	let reason;
	const length = session.seq;
	for (let seq = firstSeq; seq < length; seq++) {
		const event = session.eventAt(SessionSeq(seq));
		if (event === void 0) continue;
		if (event.type === "turn/start") {
			started = true;
			continue;
		}
		if (!started) continue;
		if (event.type === "assistant/message") {
			const joined = event.data.message.content
				.filter((block) => block.type === "text")
				.map((block) => block.text)
				.join("");
			if (joined !== "") text = joined;
		}
		if (event.type === "turn/end") reason = event.data.reason;
	}
	return { text, reason };
}

/** Stream reasoning to stderr (same as original headless). */
function streamReasoning(ctx, agent, stderr) {
	let open = false;
	let endsWithNewline = true;
	const close = () => {
		if (!open) return;
		if (!endsWithNewline) stderr.write("\n");
		open = false;
		endsWithNewline = true;
	};
	const dispose = ctx.on("agent/assistant-stream", ({ agent: subject, frame }) => {
		if (subject !== agent) return;
		if (frame.type === "start") { close(); return; }
		if (frame.type === "end") { close(); return; }
		const chunk = frame.chunk;
		switch (chunk.type) {
			case "reasoning-delta":
				if (chunk.text === "") return;
				if (!open) { stderr.write("dsh: reasoning:\n"); open = true; }
				stderr.write(chunk.text);
				endsWithNewline = chunk.text.endsWith("\n");
				return;
			case "block-start":
				if (chunk.blockType !== "reasoning") close();
				return;
			case "block-end":
				if (chunk.block.type !== "reasoning") close();
				return;
			case "usage": return;
			case "text-delta":
			case "tool-call-delta":
			case "finish":
				close(); return;
			default: return;
		}
	});
	return () => { dispose(); close(); };
}

function fail(io, error) {
	io.stderr.write(`dsh: ${error instanceof Error ? error.message : String(error)}\n`);
	io.exit(1);
}

/**
 * Run one task: create a new agent or resume a persisted one.
 * Prints the session UUID to stderr as `dsh: session: <uuid>` after completion.
 */
async function run(ctx, config, io) {
	await ctx.get("loader")?.await();
	const agents = ctx.get("agents");
	const defaultModel = ctx.get("agentDefaultModel");
	const sessions = ctx.get("sessions");
	if (agents === void 0 || defaultModel === void 0 || sessions === void 0) return;

	const selection = defaultModel.currentSelection();
	const agentBase = {
		meta: { cwd: process.cwd() },
		agentOptions: {
			provider: selection.provider,
			model: selection.model
		},
		setup: (agentCtx) => {
			installModelSelection(agentCtx, {
				current: selection,
				assembled: void 0
			});
		}
	};

	let agent;
	if (config.resume) {
		// Resume: load persisted session by UUID
		const resumeId = brandString(config.resume);
		({ agent } = await agents.resume({
			...agentBase,
			resumeSessionId: resumeId
		}));
		io.stderr.write(`dsh: resumed session ${config.resume}\n`);
	} else {
		// New session
		({ agent } = await agents.create({
			...agentBase,
			sessionId: brandString(`session-${randomUUID()}`)
		}));
	}

	await agent.whenIdle();
	const firstSeq = agent.session.seq;
	const stopReasoning = streamReasoning(ctx, agent, io.stderr);
	try {
		agent.followup(createUserMessage({
			content: [{ type: "text", text: config.task }],
			source: { kind: "user" }
		}));
		await agent.whenIdle();
	} finally {
		stopReasoning();
	}
	await sessions.flush(agent.session);

	// Print session UUID to stderr for the next resume call
	const uuid = sessionUuid(agent.session.id);
	io.stderr.write(`dsh: session: ${uuid}\n`);

	const outcome = summarize(agent.session, firstSeq);
	io.stdout.write(outcome.text + "\n");
	if (outcome.reason?.kind === "error") {
		io.stderr.write(`dsh: ${outcome.reason.error.code}: ${outcome.reason.error.message}\n`);
	}
	io.exit(outcome.reason?.kind === "completed" ? 0 : 1);
}

/** Mount the one-shot driver with resume support. */
function apply(ctx, config) {
	const exit = ctx.get("appExit");
	if (exit === void 0) throw new Error("headless-resume-runner: the launcher must provide ctx.appExit");
	const io = { stdout: internals.stdout, stderr: internals.stderr, exit };
	run(ctx, config, io).catch((error) => fail(io, error));
}

export { Config, apply, inject, internals, name };
