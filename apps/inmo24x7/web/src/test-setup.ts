import { configure } from "@testing-library/react";

// CI runners can be slow (the first test of a file also pays for the imports): wait up to
// 5 s for findBy* and waitFor, not Testing Library's 1 s.
configure({ asyncUtilTimeout: 5_000 });
