# Changelog

## [0.1.4](https://github.com/furedea/agent-config/compare/v0.1.3...v0.1.4) (2026-11-13)


### Features

* **hooks:** allow furedea review replies and mutation-free GraphQL queries ([#188](https://github.com/furedea/agent-config/issues/188)) ([a616ba2](https://github.com/furedea/agent-config/commit/a616ba2262001908f1026acea855dd5dfc13b105))
* **hooks:** judge && lists and filtered pipelines of gh and herdr commands ([#187](https://github.com/furedea/agent-config/issues/187)) ([5b98db8](https://github.com/furedea/agent-config/commit/5b98db8f4a5a406d34af54295808f7f3419c1cbb))

## [0.1.3](https://github.com/furedea/agent-config/compare/v0.1.2...v0.1.3) (2026-11-12)


### Bug Fixes

* **hooks:** report why a merged branch's worktree is kept ([#184](https://github.com/furedea/agent-config/issues/184)) ([5164b3a](https://github.com/furedea/agent-config/commit/5164b3a616072953b8103f639153248e3353a8bf))

## [0.1.2](https://github.com/furedea/agent-config/compare/v0.1.1...v0.1.2) (2026-11-12)


### Features

* **hooks:** add Go and Rust model rules with eval fixtures ([#158](https://github.com/furedea/agent-config/issues/158)) ([9731488](https://github.com/furedea/agent-config/commit/973148896e9e7031fc1f50fa9842f0b817293db2))
* **hooks:** show model-rule timing and skip rule fixtures ([#157](https://github.com/furedea/agent-config/issues/157)) ([d0c32ae](https://github.com/furedea/agent-config/commit/d0c32aecf3aa56130307d3e2fc33310a07f8b043))
* **hooks:** show the model rules as one result line with cost ([#170](https://github.com/furedea/agent-config/issues/170)) ([41b9033](https://github.com/furedea/agent-config/commit/41b90332b1a1df9d8a12f496fe272a63d73fab53))


### Bug Fixes

* **hooks:** allow a jq filter after read-only GraphQL queries ([#180](https://github.com/furedea/agent-config/issues/180)) ([cfb80d8](https://github.com/furedea/agent-config/commit/cfb80d89010d26cdf2f235a060ff005a1f309722))
* **hooks:** keep model-rule eval fixtures out of Stop test verification ([#160](https://github.com/furedea/agent-config/issues/160)) ([a4f1c6c](https://github.com/furedea/agent-config/commit/a4f1c6cdc645d081e63744f2ea29ba30a86af273))
* **hooks:** read paths literally in every jev-lint child process ([#173](https://github.com/furedea/agent-config/issues/173)) ([0d2c683](https://github.com/furedea/agent-config/commit/0d2c6831de4271cd9efc5d9fc532ac4c995aec62))
* **hooks:** remove model-rule false positives with principles and eval fixtures ([#163](https://github.com/furedea/agent-config/issues/163)) ([b07fc4e](https://github.com/furedea/agent-config/commit/b07fc4e5ed4d332b78664e59878beeeffc803b3f))
* **hooks:** report one count per runner in the Stop test lines ([#177](https://github.com/furedea/agent-config/issues/177)) ([0f36b82](https://github.com/furedea/agent-config/commit/0f36b826e2e702090702c53d6405523fec5c7687))
* **hooks:** take the model-rule cached count from the dry-run plan ([#167](https://github.com/furedea/agent-config/issues/167)) ([c87fdfd](https://github.com/furedea/agent-config/commit/c87fdfda19b0170e5513952a877484506c7415b8))

## [0.1.1](https://github.com/furedea/agent-config/compare/v0.1.0...v0.1.1) (2026-11-11)


### Features

* **hooks:** judge session changes with jev-lint model rules at Stop ([#150](https://github.com/furedea/agent-config/issues/150)) ([946e976](https://github.com/furedea/agent-config/commit/946e976806586c75e9ba6e1268902ae60a39ed16))


### Bug Fixes

* **hooks:** ask for zsh's $=name and $~name expansions ([#152](https://github.com/furedea/agent-config/issues/152)) ([9255c87](https://github.com/furedea/agent-config/commit/9255c87eca08c0ea51b15627060655ed88cb33cc))
* **hooks:** judge a ~user path by the secret-path rules of the own home ([#129](https://github.com/furedea/agent-config/issues/129)) ([64221f6](https://github.com/furedea/agent-config/commit/64221f6f244e25810e601172fe4d5d4364992890))
* **hooks:** match static words by their single-quoted form in precise command rules ([#147](https://github.com/furedea/agent-config/issues/147)) ([c432a20](https://github.com/furedea/agent-config/commit/c432a204e97a39eef71fda6cf36bc40f346a0773))
* **hooks:** run verification tools through the flake dev shell ([#132](https://github.com/furedea/agent-config/issues/132)) ([63dd2f5](https://github.com/furedea/agent-config/commit/63dd2f50e1fea44d9e0a69a1ff9a8f4ac829fd5e))
* **hooks:** start trusted model-rule programs and send only in-repository regular files ([#156](https://github.com/furedea/agent-config/issues/156)) ([183496b](https://github.com/furedea/agent-config/commit/183496b5c363a5936741be91cc8a2a8a73b29823))

## 0.1.0 (2026-11-10)


### Features

* add devin provider to hooks.json with hook adapter (furedea/dotfiles[#136](https://github.com/furedea/agent-config/issues/136)) ([5bc5550](https://github.com/furedea/agent-config/commit/5bc5550483938488e50de9d2834e62588a5dc6cf))
* add git-commit-split skill ([35f4e16](https://github.com/furedea/agent-config/commit/35f4e16e2a8c02a3e926a2fde3e3a5f811e3be22))
* add Hermes Agent and pi hook providers (furedea/dotfiles[#138](https://github.com/furedea/agent-config/issues/138)) ([ed3a774](https://github.com/furedea/agent-config/commit/ed3a7747938252dafaf45cf54ac2745efbbdd844))
* add lock-settings, report-doc-conflict, and report-hook-block skills ([35b8585](https://github.com/furedea/agent-config/commit/35b8585830e23b1b7aeee84da5afec97bde975fb))
* **agents:** add Rust style skill ([a82df41](https://github.com/furedea/agent-config/commit/a82df4138236cd854da1253e20fe7d7406774e38))
* **agents:** allow cd, sed, awk, xargs, cp, and mv under the sandbox (furedea/dotfiles[#165](https://github.com/furedea/agent-config/issues/165)) ([5783f87](https://github.com/furedea/agent-config/commit/5783f873c159f5d2722a83a6245b05c30e68f380))
* **agents:** bootstrap the harness on servers without Nix ([80a0f9b](https://github.com/furedea/agent-config/commit/80a0f9b0f0835823cc43d5cb838ec599c6dd1486))
* **agents:** chain git add, status, commit, and push outside the sandbox (furedea/dotfiles[#169](https://github.com/furedea/agent-config/issues/169)) ([dd5a05c](https://github.com/furedea/agent-config/commit/dd5a05c9259770e573af25aa9227622fe5272e5a))
* **agents:** Codex implements, Claude reviews, and lanes clean up opened workspaces (furedea/dotfiles[#266](https://github.com/furedea/agent-config/issues/266)) ([c9a3fd9](https://github.com/furedea/agent-config/commit/c9a3fd9248bfe3aa582192e6513caafda5b11859))
* **agents:** generate hook settings from nix ([b20d592](https://github.com/furedea/agent-config/commit/b20d592a073f31f3b4e4cf662bc095cd0a578d8b))
* **agents:** hand approved lanes to Herdr task worktree sessions (furedea/dotfiles[#184](https://github.com/furedea/agent-config/issues/184)) ([58a591f](https://github.com/furedea/agent-config/commit/58a591fe1f9e60f393fa6e14c46a46b416f831a2))
* **agents:** own personal agent source (furedea/dotfiles[#52](https://github.com/furedea/agent-config/issues/52)) ([51060b1](https://github.com/furedea/agent-config/commit/51060b143dff80eeec775010d74c0e2945355d31))
* **agents:** permit commands by reversibility (furedea/dotfiles[#124](https://github.com/furedea/agent-config/issues/124)) ([bb96256](https://github.com/furedea/agent-config/commit/bb962566fbccc5fa9abf5081cd6826b0e375f48f))
* **agents:** run agent git inside the sandbox with unsigned commits (furedea/dotfiles[#172](https://github.com/furedea/agent-config/issues/172)) ([1492f3e](https://github.com/furedea/agent-config/commit/1492f3e565cd18da350f5b1f118e8286056aa3cd))
* **agents:** start Herdr Claude lanes on Sonnet at medium effort (furedea/dotfiles[#257](https://github.com/furedea/agent-config/issues/257)) ([3caf8d5](https://github.com/furedea/agent-config/commit/3caf8d5600224529a6472b7c3a8446b28b590d34))
* **agents:** write PR bodies inline and close lanes' parent workspaces (furedea/dotfiles[#211](https://github.com/furedea/agent-config/issues/211)) ([8c6df4e](https://github.com/furedea/agent-config/commit/8c6df4e4a1d307dbf554208c0c787186e08a1ec7))
* **claude:** close the sandbox escape and reach the Nix daemon inside (furedea/dotfiles[#191](https://github.com/furedea/agent-config/issues/191)) ([b61f2ac](https://github.com/furedea/agent-config/commit/b61f2ac3bd631f8f5f3e719a5b0e3f4e6e8ac1e3))
* **claude:** let Go CLIs verify TLS inside the sandbox (furedea/dotfiles[#167](https://github.com/furedea/agent-config/issues/167)) ([282b3d2](https://github.com/furedea/agent-config/commit/282b3d2b8beffd592da6727d83aa9618afd38a5b))
* **claude:** let sandboxed commands listen on local ports (furedea/dotfiles[#206](https://github.com/furedea/agent-config/issues/206)) ([36c09d2](https://github.com/furedea/agent-config/commit/36c09d27aaee75f1330eb86533ac76c52ba9ab39))
* **claude:** run the Codex plugin companion outside the sandbox (furedea/dotfiles[#232](https://github.com/furedea/agent-config/issues/232)) ([0255159](https://github.com/furedea/agent-config/commit/02551590e313f86c40ac90f609150bbb361ded9a))
* **codex:** let Codex write, test, and deliver inside the sandbox (furedea/dotfiles[#200](https://github.com/furedea/agent-config/issues/200)) ([33a0a82](https://github.com/furedea/agent-config/commit/33a0a82269dff6c758be615946a6658e10b86c0d))
* compose Herdr and Moshi agent hooks (furedea/dotfiles[#33](https://github.com/furedea/agent-config/issues/33)) ([4951ee8](https://github.com/furedea/agent-config/commit/4951ee8fc82162273a9233bc79b2659797b417aa))
* **dsh:** add the dsh hook adapter ([#101](https://github.com/furedea/agent-config/issues/101)) ([db86f57](https://github.com/furedea/agent-config/commit/db86f57d9af3292c9a8dba4f402e765adc4fb060))
* **git-commit-split:** accept mode from slash-command argument ([10c3ef7](https://github.com/furedea/agent-config/commit/10c3ef70de84b645fb1a194fc3c9a8827a52ef86))
* **git-commit-split:** modularize commit splitting workflow with branch ([bab6f19](https://github.com/furedea/agent-config/commit/bab6f193cf519ac36bb51e3505b31251465ae119))
* **github:** add repository creation script ([1a7910b](https://github.com/furedea/agent-config/commit/1a7910b78f6062b0ebd83e41edf96c31d047206c))
* **hermes:** use Apple Mail for mail access (furedea/dotfiles[#69](https://github.com/furedea/agent-config/issues/69)) ([94268fa](https://github.com/furedea/agent-config/commit/94268fad9b440fa87063f091a8214224085d0e81))
* **hooks:** add related test selection rules ([2aca101](https://github.com/furedea/agent-config/commit/2aca101d0b9ae96fe36b86d77d23ed3ae0a1f69c))
* **hooks:** add shared audit and command guard hooks ([6ab33b5](https://github.com/furedea/agent-config/commit/6ab33b59125f580b1debbd5ca5e4f8c8f5b95dbf))
* **hooks:** allow read-only local curl diagnostics and log syntax ask kinds (furedea/dotfiles[#287](https://github.com/furedea/agent-config/issues/287)) ([83cd643](https://github.com/furedea/agent-config/commit/83cd6431f0ae7810531edeb33c67aa6aef7095fe))
* **hooks:** ask before an agent adds a lint suppression (furedea/dotfiles[#214](https://github.com/furedea/agent-config/issues/214)) ([b767665](https://github.com/furedea/agent-config/commit/b76766519c5860ecfbebfa40e1ed4a16d9ce9120))
* **hooks:** ask only for effects that escape the sandbox (furedea/dotfiles[#163](https://github.com/furedea/agent-config/issues/163)) ([21409a5](https://github.com/furedea/agent-config/commit/21409a5c3054378c899b4f4c1021d756d9c7fb98))
* **hooks:** block destructive non-push git operations ([cc02cb4](https://github.com/furedea/agent-config/commit/cc02cb416c5d1e535ce5d83cbd5def8fc36ca2ea))
* **hooks:** escalate unrecognized command forms to a prompt (furedea/dotfiles[#159](https://github.com/furedea/agent-config/issues/159)) ([e30de17](https://github.com/furedea/agent-config/commit/e30de1725e8e8725422e03a117cf75280958bfcd))
* **hooks:** fast-forward main after cleaning up merged lanes (furedea/dotfiles[#210](https://github.com/furedea/agent-config/issues/210)) ([f8a60af](https://github.com/furedea/agent-config/commit/f8a60af40acf9418cc8e0aff9f0e7dd5eb55cd06))
* **hooks:** honor project allow rules only from trusted owners ([#33](https://github.com/furedea/agent-config/issues/33)) ([305d391](https://github.com/furedea/agent-config/commit/305d391da02c0599818e39a29402a6bc9e9e331a))
* **hooks:** improve lint-format feedback across providers ([8a512f6](https://github.com/furedea/agent-config/commit/8a512f6fce181d116c6ea319af2d44266baf91bc))
* **hooks:** judge heredocs, substitutions, loops, and redirections structurally (furedea/dotfiles[#175](https://github.com/furedea/agent-config/issues/175)) ([9276283](https://github.com/furedea/agent-config/commit/92762836e2e3b593af247b82875477b91507e245))
* **hooks:** let sessions lock flake inputs and close their own lanes (furedea/dotfiles[#208](https://github.com/furedea/agent-config/issues/208)) ([f109b49](https://github.com/furedea/agent-config/commit/f109b4998b0f03be4c2451fb6567ccb571e8f99d))
* **hooks:** let the parent run cleanup_worktrees.py after merge (furedea/dotfiles[#300](https://github.com/furedea/agent-config/issues/300)) ([fc44c74](https://github.com/furedea/agent-config/commit/fc44c745c0b48d4df466695ea761e9c3cf6a029b))
* **hooks:** remove merged task worktrees and branches at session start (furedea/dotfiles[#185](https://github.com/furedea/agent-config/issues/185)) ([2701e0b](https://github.com/furedea/agent-config/commit/2701e0be671bf125c94adf8285d4be75f2c1eff6))
* **hooks:** replay recent commands through the hooks (furedea/dotfiles[#199](https://github.com/furedea/agent-config/issues/199)) ([2ed4984](https://github.com/furedea/agent-config/commit/2ed4984705a912305835cbf25d522bdbaa6cf50a))
* **hooks:** report ast-grep rule findings after an edit ([#119](https://github.com/furedea/agent-config/issues/119)) ([ff91d8c](https://github.com/furedea/agent-config/commit/ff91d8ce0aad48a72f900ec37aae891467781733))
* **hooks:** review only commands that reach past the sandbox (furedea/dotfiles[#178](https://github.com/furedea/agent-config/issues/178)) ([40c97da](https://github.com/furedea/agent-config/commit/40c97dadfea76b07fee8b24251c0d95cc7530fef))
* **hooks:** run zizmor offline after workflow edits (furedea/dotfiles[#295](https://github.com/furedea/agent-config/issues/295)) ([79b66a6](https://github.com/furedea/agent-config/commit/79b66a64682fe1444b25f3fafbdef899c9a8e516))
* **hooks:** scan with the shared ast-grep rules shipped beside the hooks ([#121](https://github.com/furedea/agent-config/issues/121)) ([35a9270](https://github.com/furedea/agent-config/commit/35a9270466d4a9a125837df59b7eafdd7670c7c1))
* **hooks:** support Go projects in formatting, verification, and permissions ([#57](https://github.com/furedea/agent-config/issues/57)) ([5506f3c](https://github.com/furedea/agent-config/commit/5506f3c9ece6c2a5e2abcd715e24f6567cec0de0))
* **hooks:** verification selection, unified patch input, formatter/linter ordering (furedea/dotfiles[#144](https://github.com/furedea/agent-config/issues/144)) ([99a825b](https://github.com/furedea/agent-config/commit/99a825b9d2787b0dcab029ceb3160d02c874ac90))
* **lint:** add the first ten ast-grep rules and drop the prose they replace ([#117](https://github.com/furedea/agent-config/issues/117)) ([c235eb5](https://github.com/furedea/agent-config/commit/c235eb50ae025cd24f8c003a09321bddf779b5eb))
* **nix:** expose the plain agents path as passthru.tree of agent-source ([#94](https://github.com/furedea/agent-config/issues/94)) ([63632e4](https://github.com/furedea/agent-config/commit/63632e44510362bbd204a7b482527f7d04e3fae0))
* **security:** add a program_path option that pins a rule's program to one absolute path ([#61](https://github.com/furedea/agent-config/issues/61)) ([d629ca9](https://github.com/furedea/agent-config/commit/d629ca9d48114f8126c4f814cb964d9c6226a2e7))
* **security:** allow agent-browser and agent-desktop except named risky forms ([#63](https://github.com/furedea/agent-config/issues/63)) ([8dc8da5](https://github.com/furedea/agent-config/commit/8dc8da5117e53d34cd059f75f8c3194f0c67ebce))
* **security:** allow cargo caches, crates.io, and OSV in the sandbox ([#60](https://github.com/furedea/agent-config/issues/60)) ([2f29423](https://github.com/furedea/agent-config/commit/2f2942333949b3b2195fba993aea752f2203088a))
* **security:** allow Go caches and module hosts in the sandbox ([#58](https://github.com/furedea/agent-config/issues/58)) ([4b3a35c](https://github.com/furedea/agent-config/commit/4b3a35ce35c0c0b43d354ab805bcd847b661cc3f))
* **security:** ask for every docker form the allowlist does not list ([#54](https://github.com/furedea/agent-config/issues/54)) ([764374f](https://github.com/furedea/agent-config/commit/764374f7b7ebc59d6aca8598ea8e5c68ce23ab36))
* **security:** deny the 1Password CLI and keep the Codex login in the keyring ([#52](https://github.com/furedea/agent-config/issues/52)) ([0580825](https://github.com/furedea/agent-config/commit/05808259b66ba61ada607ec0fe3b1aa5d873c32c))
* **skill-auditor:** support Codex audit workflow ([0d88c3f](https://github.com/furedea/agent-config/commit/0d88c3fb81cb4b1f394744f557151074ab8cc368))
* **skills:** add measurement-evidence and change-type evidence to tsdd ([#70](https://github.com/furedea/agent-config/issues/70)) ([85714b5](https://github.com/furedea/agent-config/commit/85714b570c6d05ce912bc4f4288e02c4e2233bca))
* **skills:** clarify names and add Herdr delegation (furedea/dotfiles[#127](https://github.com/furedea/agent-config/issues/127)) ([e6576ba](https://github.com/furedea/agent-config/commit/e6576baba5ea6cdf810f80b3340213c454312069))
* **skill:** skill-auditor by nyosegawa/skills/skill-auditor ([f191132](https://github.com/furedea/agent-config/commit/f191132aee9591bb5db747e411d81cf235cc2ecb))
* **skills:** render provider-specific SKILL.md frontmatter ([44325e5](https://github.com/furedea/agent-config/commit/44325e56490942fc7c6aae46df5afb2a63782da0))
* **statusline:** render the status on one line (furedea/dotfiles[#110](https://github.com/furedea/agent-config/issues/110)) ([03ad85e](https://github.com/furedea/agent-config/commit/03ad85e89de28615617802193451deb5f7a0ea32))
* update bash-style skill instructions ([9ab1d65](https://github.com/furedea/agent-config/commit/9ab1d657b6b591e7eac57421d2ccfea0dc76524a))
* update github-ci-init skill templates ([d238f51](https://github.com/furedea/agent-config/commit/d238f51a3806a6671be832240efec288ce610378))
* verify agent changes through native hooks (furedea/dotfiles[#106](https://github.com/furedea/agent-config/issues/106)) ([923b0ae](https://github.com/furedea/agent-config/commit/923b0aea8a8692ba09cb1df8db159a0683aae96f))


### Bug Fixes

* **agents:** accept generated command permissions (furedea/dotfiles[#66](https://github.com/furedea/agent-config/issues/66)) ([0af9650](https://github.com/furedea/agent-config/commit/0af965093676c91cb19456fcdccef46b6df03ab0))
* **agents:** allow gh api reads that pass --allow-escape-sequences (furedea/dotfiles[#265](https://github.com/furedea/agent-config/issues/265)) ([e732939](https://github.com/furedea/agent-config/commit/e732939e0f822056d8d9b1a1e2657406f02585e8))
* **agents:** apply harness review findings (furedea/dotfiles[#149](https://github.com/furedea/agent-config/issues/149)) ([c8a51d7](https://github.com/furedea/agent-config/commit/c8a51d7449f0961816481aef7dd9df87ffd12822))
* **agents:** cap Codex session-end timeout ([2f29a7e](https://github.com/furedea/agent-config/commit/2f29a7e6a6c03b6e86e4ca03c19c48d7809b0008))
* **agents:** deny codex-companion calls the sandbox exclusion cannot match (furedea/dotfiles[#269](https://github.com/furedea/agent-config/issues/269)) ([25518ab](https://github.com/furedea/agent-config/commit/25518ab5b04fdee1d351515070c7c204165f18b6))
* **agents:** harden hooks and separate workflow responsibilities (furedea/dotfiles[#128](https://github.com/furedea/agent-config/issues/128)) ([7e508c4](https://github.com/furedea/agent-config/commit/7e508c44f0858e9fcc43807c452eec28dc9680fa))
* **agents:** let pnpm fetch from the npm registry inside the sandbox (furedea/dotfiles[#222](https://github.com/furedea/agent-config/issues/222)) ([ac114e8](https://github.com/furedea/agent-config/commit/ac114e82c1ff7d724b68a8cd321fe89e2a7cad4f))
* **agents:** let the forbidden rule admit Sonnet lane arguments (furedea/dotfiles[#259](https://github.com/furedea/agent-config/issues/259)) ([f1b29a9](https://github.com/furedea/agent-config/commit/f1b29a9ce568ebde5da913a1a3b2093156e2e102))
* **agents:** make the bootstrap hint work for POSIX login shells ([c2667fa](https://github.com/furedea/agent-config/commit/c2667fa7968fd90b90ec7401cd4c32a6347e2925))
* **agents:** stop asking for commands the hooks can prove safe (furedea/dotfiles[#242](https://github.com/furedea/agent-config/issues/242)) ([a93d241](https://github.com/furedea/agent-config/commit/a93d24199954823a9fcb430562a90af9b8485c10))
* **agents:** wait for hook state locks instead of failing with EAGAIN (furedea/dotfiles[#285](https://github.com/furedea/agent-config/issues/285)) ([673c108](https://github.com/furedea/agent-config/commit/673c10857bfc0c100a6d3c01e242a9710f7dd113))
* allow secret scanner hook files ([bca4207](https://github.com/furedea/agent-config/commit/bca4207adb5763cec69b17e12400996798f5bc38))
* **bootstrap:** give Codex the agent GitHub token settings and run the bootstrap in CI ([#21](https://github.com/furedea/agent-config/issues/21)) ([25de080](https://github.com/furedea/agent-config/commit/25de080dade11bf0da0e69c06ba2862ef263b69c))
* **bootstrap:** keep Neovim's fallback nvim.log out of the working directory ([#43](https://github.com/furedea/agent-config/issues/43)) ([3c9fc5c](https://github.com/furedea/agent-config/commit/3c9fc5cf0dab854421929f6a1492d01989d6ea3d))
* **bootstrap:** make the server bootstrap behave like the Nix hosts ([#15](https://github.com/furedea/agent-config/issues/15)) ([4554dec](https://github.com/furedea/agent-config/commit/4554dec766f4196be4a7c479959b16e74fce99b2))
* **bootstrap:** print actionable profile and legacy-file messages only when needed ([#49](https://github.com/furedea/agent-config/issues/49)) ([1918254](https://github.com/furedea/agent-config/commit/1918254bc64af8dfc59fb1bce8733392f1de14cd))
* **bootstrap:** target the login profile bash actually reads ([#50](https://github.com/furedea/agent-config/issues/50)) ([0dae5bf](https://github.com/furedea/agent-config/commit/0dae5bf17540767c9e3788e5303eaa6442efdc1d))
* **bootstrap:** verify downloaded tools against pinned checksums ([#111](https://github.com/furedea/agent-config/issues/111)) ([1744df3](https://github.com/furedea/agent-config/commit/1744df353b86973968401873bcd49b2eda877e3c))
* **ci:** install the locked agent-harness instead of reading it from the flake ([bc2395b](https://github.com/furedea/agent-config/commit/bc2395b56561d8e2480cab8917f39d576c84d42e))
* **ci:** provide the shell format config and locked JavaScript tools ([dd59634](https://github.com/furedea/agent-config/commit/dd5963428deebd05124bba647a3f9e952af66880))
* **claude:** trust only the CA store bundled with Claude Code (furedea/dotfiles[#284](https://github.com/furedea/agent-config/issues/284)) ([34be271](https://github.com/furedea/agent-config/commit/34be271f0e65844a47f76f1d990fc4894bea1b07))
* **codex:** fall back to auth.json when no keyring is available ([#62](https://github.com/furedea/agent-config/issues/62)) ([79b6ceb](https://github.com/furedea/agent-config/commit/79b6ceb4da8cf42f0f49cfc431b17acbb8c1c89d))
* correct agent tooling and Hister activation (furedea/dotfiles[#85](https://github.com/furedea/agent-config/issues/85)) ([4bab065](https://github.com/furedea/agent-config/commit/4bab06546c43893c58de9b3e0ff2c29a52e65708))
* honor pytest testpaths and bootstrap bats on servers (furedea/dotfiles[#116](https://github.com/furedea/agent-config/issues/116)) ([b17b59e](https://github.com/furedea/agent-config/commit/b17b59ea34847e85690ef0eaef6360abc3fe0c47))
* **hooks:** allow double quoted commit messages ([fc4afd4](https://github.com/furedea/agent-config/commit/fc4afd45101f0d5b8d347183eda26514ee386dbf))
* **hooks:** bound curl -o, -d and -H in the localhost rule (furedea/dotfiles[#291](https://github.com/furedea/agent-config/issues/291)) ([7c9db8a](https://github.com/furedea/agent-config/commit/7c9db8a1ed71b73c323b10cf7e118cb6966be2d7))
* **hooks:** close shell-syntax bypasses of the guard hooks ([#11](https://github.com/furedea/agent-config/issues/11)) ([c6aacdf](https://github.com/furedea/agent-config/commit/c6aacdf4a27435ea0cffbf1a6689810a200d6ee3))
* **hooks:** close the guard contract gaps from [#11](https://github.com/furedea/agent-config/issues/11) review ([#31](https://github.com/furedea/agent-config/issues/31)) ([db318db](https://github.com/furedea/agent-config/commit/db318db6522e7385cb5b4e483af842fa42899c7d))
* **hooks:** deny codex-companion calls whose text holds a dollar sign or backtick (furedea/dotfiles[#290](https://github.com/furedea/agent-config/issues/290)) ([f37c317](https://github.com/furedea/agent-config/commit/f37c317a2afd0b13ae16b02af80e42da66fba9fa))
* **hooks:** find GNU grep on PATH instead of the first grep (furedea/dotfiles[#193](https://github.com/furedea/agent-config/issues/193)) ([99ba317](https://github.com/furedea/agent-config/commit/99ba317aa541cbe4aa325fb1777117db7dcc4123))
* **hooks:** format without dotfiles-installed dprint and prettier configs ([#16](https://github.com/furedea/agent-config/issues/16)) ([db21f55](https://github.com/furedea/agent-config/commit/db21f555e6b983cc3d1ccacdafb3cb97274ed225))
* **hooks:** ignore git-ignored sources when judging a project removed ([#22](https://github.com/furedea/agent-config/issues/22)) ([97c6b93](https://github.com/furedea/agent-config/commit/97c6b93944eaeacb98887037af2ea89bd1a19dd5))
* **hooks:** ignore prose arguments when matching forbidden patterns (furedea/dotfiles[#189](https://github.com/furedea/agent-config/issues/189)) ([d2049d6](https://github.com/furedea/agent-config/commit/d2049d6f1a2f5608cefe6ca918f5a7ed33cd0f33))
* **hooks:** judge each command as one line with any grep (furedea/dotfiles[#196](https://github.com/furedea/agent-config/issues/196)) ([202f937](https://github.com/furedea/agent-config/commit/202f937ee3e77d8e99e6fa62df2147ea1ad9a092))
* **hooks:** keep merged worktrees holding non-regenerable ignored files ([#29](https://github.com/furedea/agent-config/issues/29)) ([ac03cfa](https://github.com/furedea/agent-config/commit/ac03cfa36f781ed956aaae6633f85627e6754684))
* **hooks:** keep the first grep when no GNU grep is on PATH (furedea/dotfiles[#195](https://github.com/furedea/agent-config/issues/195)) ([a0e6a2f](https://github.com/furedea/agent-config/commit/a0e6a2f82293ed43036967a7a10dbe352278c1df))
* **hooks:** keep the verification snapshot from locking out symlinked or large worktrees ([#66](https://github.com/furedea/agent-config/issues/66)) ([7d13f0e](https://github.com/furedea/agent-config/commit/7d13f0eb9c8680afb5f92289db67736947d429bd))
* **hooks:** let cleanup_worktrees remove Claude Code session files ([#36](https://github.com/furedea/agent-config/issues/36)) ([0a910bc](https://github.com/furedea/agent-config/commit/0a910bc94af9569f3a1863ab1bb8504133f3d3cf))
* **hooks:** let cleanup_worktrees tests choose the untrusted locations (furedea/dotfiles[#306](https://github.com/furedea/agent-config/issues/306)) ([e82980e](https://github.com/furedea/agent-config/commit/e82980e28e2f98fb25dcb72c307373299f0aa99c))
* **hooks:** let GitHub API reads take an unquoted jq filter (furedea/dotfiles[#198](https://github.com/furedea/agent-config/issues/198)) ([5b6210a](https://github.com/furedea/agent-config/commit/5b6210ad235038d1e889ff45b38ffb89151e1d8f))
* **hooks:** make stop verification reliable (furedea/dotfiles[#81](https://github.com/furedea/agent-config/issues/81)) ([04a33dd](https://github.com/furedea/agent-config/commit/04a33dd3811117781679b0c4255c943a686f2676))
* **hooks:** preserve verification evidence (furedea/dotfiles[#87](https://github.com/furedea/agent-config/issues/87)) ([4b5b9c2](https://github.com/furedea/agent-config/commit/4b5b9c2f82dc2bd3ffbf63087a709e1a922fa1d9))
* **hooks:** redirect sandbox-failing Git forms and drop covered prompts (furedea/dotfiles[#180](https://github.com/furedea/agent-config/issues/180)) ([34e39a7](https://github.com/furedea/agent-config/commit/34e39a70651d84bd31e56c055a51d10b3fd0b914))
* **hooks:** resolve Rust integration test targets inside tests subdirectories (furedea/dotfiles[#304](https://github.com/furedea/agent-config/issues/304)) ([2ccf547](https://github.com/furedea/agent-config/commit/2ccf547cbfcaa5c0cb11e0ae881a11760b65f4ae))
* **hooks:** respect project formatters and bound diagnostics (furedea/dotfiles[#131](https://github.com/furedea/agent-config/issues/131)) ([30e83cf](https://github.com/furedea/agent-config/commit/30e83cffe2e4c630413aa310189bdb92de1db823))
* **hooks:** scope generic secret regex to quoted values ([fc09292](https://github.com/furedea/agent-config/commit/fc09292a544137a113da4056efb415f1be38218e))
* **hooks:** silence successful hook execution ([795d8f0](https://github.com/furedea/agent-config/commit/795d8f06f9a6a6e4b4b06c0a7cde7b763fd7f127))
* **hooks:** skip JavaScript triggers in projects without JavaScript tests (furedea/dotfiles[#161](https://github.com/furedea/agent-config/issues/161)) ([dc80e28](https://github.com/furedea/agent-config/commit/dc80e28d0a7065eed5ffb537134cb9039da905cb))
* **hooks:** skip verification for a language whose project was removed ([#6](https://github.com/furedea/agent-config/issues/6)) ([4a9f325](https://github.com/furedea/agent-config/commit/4a9f32541ad221a4c824eabc2a53684421efd455))
* **hooks:** support relocated harness assets (furedea/dotfiles[#82](https://github.com/furedea/agent-config/issues/82)) ([59057bc](https://github.com/furedea/agent-config/commit/59057bc6237541112dcafd0814a8ee36d9870f07))
* **hooks:** treat any gh api call without write flags as a read (furedea/dotfiles[#201](https://github.com/furedea/agent-config/issues/201)) ([3ecb215](https://github.com/furedea/agent-config/commit/3ecb215ffaa722dedeaa7059a4b3a77388a7cf38))
* **hooks:** treat glob characters inside double quotes as literal for literal_words rules ([#41](https://github.com/furedea/agent-config/issues/41)) ([174a7f9](https://github.com/furedea/agent-config/commit/174a7f91e2009f3ccd7eb58bdb7c9f079c68553c))
* **hooks:** use agent-neutral guidance ([37153ce](https://github.com/furedea/agent-config/commit/37153cecb0ac92c61c21f25d54f139e748c97d14))
* improve agent notifications and session setup (furedea/dotfiles[#92](https://github.com/furedea/agent-config/issues/92)) ([9bf2349](https://github.com/furedea/agent-config/commit/9bf234934c4933f8b502a5ebfcff0363ccad11b8))
* load secret patterns from hook directory ([ca465ef](https://github.com/furedea/agent-config/commit/ca465ef5aac666b827e6cb716290458e8e9cd7fc))
* migrate dotfiles path to ghq convention ([faff774](https://github.com/furedea/agent-config/commit/faff77411fa1268f5e0da400c4b909a7a19ced5f))
* **nix:** build CPython 3.15.2 for the ssl eMudhra denylist ([#113](https://github.com/furedea/agent-config/issues/113)) ([faba045](https://github.com/furedea/agent-config/commit/faba045700c19588c26cf6792e7fe50a4c57ae95))
* **nix:** default editor to Neovim (furedea/dotfiles[#105](https://github.com/furedea/agent-config/issues/105)) ([2a9a22a](https://github.com/furedea/agent-config/commit/2a9a22a2748dd883eb7bc4e95229c3b00a32bbff))
* resolve hook directory from bash source ([c6ca454](https://github.com/furedea/agent-config/commit/c6ca454d10f169ba610e4cd9b4e51f0b26d70d25))
* restore SSH signing and reliable Bats verification (furedea/dotfiles[#91](https://github.com/furedea/agent-config/issues/91)) ([891adce](https://github.com/furedea/agent-config/commit/891adce64f9344413624c0b189a22ef123c38ca5))
* **sandbox:** deny writes to every repository's git hooks and config (furedea/dotfiles[#298](https://github.com/furedea/agent-config/issues/298)) ([1941513](https://github.com/furedea/agent-config/commit/1941513a1ca6213844770ab31c22f640f55cb959))
* **sandbox:** match the Codex plugin script under any numeric version (furedea/dotfiles[#302](https://github.com/furedea/agent-config/issues/302)) ([a49ddc3](https://github.com/furedea/agent-config/commit/a49ddc3f3f88fa72bc77265b4b0d5e87a883ec01))
* **security:** allow the Go checksum tree head and vulnerability database in the sandbox ([#59](https://github.com/furedea/agent-config/issues/59)) ([af6e158](https://github.com/furedea/agent-config/commit/af6e15892c148ab1c6d6c39c4f1a0409037c5cc0))
* **security:** ask for every script a non-bash shell receives ([#99](https://github.com/furedea/agent-config/issues/99)) ([f88f8fd](https://github.com/furedea/agent-config/commit/f88f8fdaf62b50034904ad1c60d5442b594100c1))
* **security:** close quoted-argument and wrapper bypasses in the command guard ([#76](https://github.com/furedea/agent-config/issues/76)) ([5f72757](https://github.com/furedea/agent-config/commit/5f72757b857b0437ffca5fe85fb0216ff27078bd))
* **security:** close the remaining command guard bypasses ([#83](https://github.com/furedea/agent-config/issues/83)) ([0387739](https://github.com/furedea/agent-config/commit/03877393364210376fb915c37b5597ec588758ba))
* **security:** decide not-a-fork for project rules on hosts without gh ([#67](https://github.com/furedea/agent-config/issues/67)) ([acaa758](https://github.com/furedea/agent-config/commit/acaa75899f41a67282e267ff29967617ae59aa4c))
* **security:** keep agent-browser and agent-desktop calls inside the sandbox ([#64](https://github.com/furedea/agent-config/issues/64)) ([3f2d578](https://github.com/furedea/agent-config/commit/3f2d578213f5e1c9da2761cbd8996b9f15e80313))
* **security:** read more of the scripts handed to fish and PowerShell for deny rules ([#110](https://github.com/furedea/agent-config/issues/110)) ([2c652bb](https://github.com/furedea/agent-config/commit/2c652bbb21fc257934c0376e116e33acc1175183))
* **skills:** audit Codex skill observations (furedea/dotfiles[#88](https://github.com/furedea/agent-config/issues/88)) ([f429967](https://github.com/furedea/agent-config/commit/f429967173a9b2204a175bd2a35320e71efefdb9))
* **skills:** refine routing triggers from audit ([cef3b9c](https://github.com/furedea/agent-config/commit/cef3b9c1ec84cb60c88bf2c2c714cb6a268d4925))
* **tests:** make git test wrappers exec the real git binary (furedea/dotfiles[#310](https://github.com/furedea/agent-config/issues/310)) ([893c405](https://github.com/furedea/agent-config/commit/893c405e6801732feaeb4faea5d855035b441619))
* **tests:** stop shifting past the codex wrapper arguments ([eb0f6d7](https://github.com/furedea/agent-config/commit/eb0f6d777d98130278f088701398e3e7b0ca82ba))


### Performance Improvements

* **hooks:** evaluate policy regexes with one grep and run pytest in parallel (furedea/dotfiles[#125](https://github.com/furedea/agent-config/issues/125)) ([ce80ea3](https://github.com/furedea/agent-config/commit/ce80ea3d7b16fc869cd61aaa031da2bd5c551dbb))
