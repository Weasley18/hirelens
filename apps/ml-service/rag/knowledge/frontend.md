# Frontend, React and the browser

## React rendering and re-renders

Ask what causes a component to re-render and how they found an unnecessary one. Expect state
change, prop change, parent re-render, and context value change. A good follow-up: your
context value is an object literal, and every consumer re-renders on every parent render.
Why, and what do you do about it? Memoising the value should come up. Candidates who reach
for memo on everything without measuring are showing a habit rather than a diagnosis.

## State management choices

Ask how they decide between local state, lifted state, context, and a store. Listen for
server state being treated differently from client state — data fetched from an API has
caching, staleness and refetching concerns that a toggle does not. Candidates who put every
API response into a global store usually have not felt the cost yet.

## Effects and data fetching

Ask what goes wrong with a fetch inside an effect when the component unmounts before it
resolves, or when the dependency changes mid-flight. Expect cancellation, an ignore flag, or
a library that handles it. A strong candidate can describe a race where an older response
arrives after a newer one and overwrites it.

## Performance and bundle size

Ask what their largest bundle dependency is and how they know. Expect a bundle analyser,
code splitting at the route level, and awareness of what is loaded on first paint versus
later. Follow up on images and fonts, which dominate real-world load time more often than
JavaScript does.

## Accessibility

Ask how they would build a modal that works for keyboard and screen reader users. Focus
trapping, returning focus on close, escape to dismiss, an accessible name, and inert
background content are all signals of someone who has done it rather than read about it. A
quick probe for any frontend candidate: when is a div with an onClick handler not acceptable?

## Forms and validation

Ask where validation lives when both the client and the server need it. The answer is both,
for different reasons — the client for feedback, the server because the client can be
bypassed. Ask how they keep the two in sync; a shared schema is the strong answer.

## TypeScript in practice

Ask what they use `any` for and when they last reached for it. Then ask about typing an API
response: a strong candidate distinguishes a compile-time type assertion from runtime
validation, and knows that data crossing the network boundary needs the latter.

## CSS and layout

Ask them to explain when they use flexbox versus grid, and what a stacking context is. For
candidates claiming design implementation, ask how they handle a layout that has to work at
320px and at 2560px, and listen for intrinsic sizing and container queries rather than a
list of breakpoints.
