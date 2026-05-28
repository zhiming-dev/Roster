我想写一个project，类似于agency/model consule，my work focuses on creating a enhanced human-AI-协作 framework，就是那种这个系统就类似于一个公司，有一个master/PM角色进行做最高级别的设计（需要用户审批，批准之后即可分发给下面的expert sub-agent来执行），然后有很多个expert sub-agent 用来执行。所有的agent都会被赋予相应的skills。这种human-in-the-loop agent framework会有效减少completely autonomous agent 9秒钟删库的风险。AI之间会进行讨论（比如说我自己在进行一件复杂事情的时候，我会同时问Claude, GPT和Gemni，他们may or may not 给出一样或者不同的结论，或者侧重点不一样。然后我会把他们的结果发来发去进行讨论，就会得到更好的答案）

现阶段我开发了一个基于Playwright CLI的agent，agent可以执行用户定义的e2e tests（基本上这个expert subagent是一个QA的角色）

接下来就是开发多agent协作模式。以及（不知道有没有已有的论文了）对比，single Superman 模型(with all the skills)和这种协作framework，performance的差别.

I will also be sharing these technical insights into publications and open-source contributions for more generalizable tooling. This should help demonstrate my work has impact beyond a single employer.

（进一步把这project包装成industrial complimentary research)值得一提的是我这个project和我在微软的employment没有直接关系。我在微软的employment反而会帮助我在industry 实地测试/开发的insight


This project focuses on designing and evaluating a human-in-the-loop multi-agent AI framework for autonomous software engineering and workflow automation tasks. The system uses a hierarchical architecture in which a planning agent decomposes tasks and routes them to specialized sub-agents under explicit human approval checkpoints. The project aims to reduce reliability and safety risks associated with fully autonomous large-language-model agents, including unintended destructive actions, while improving transparency, and controllability in real-world AI deployments. Planned outputs include an open-source release on GitHub accessible to U.S. researchers, startups, and small businesses, and a peer-reviewed empirical study comparing single-model "super-agent" architectures against multi-agent collaboration with human-in-the-loop checkpoints across performance, safety, and recoverability metrics

This project directly supports my proposed endeavor by operationalizing the AI safety and controllability dimension of trustworthy AI research for the emerging class of autonomous large-language-model agents. The framework's design, with mandatory human approval gates, decomposable skill modules, and transparent task delegation, is itself a contribution to AI auditability and supports my broader proposed endeavor of developing trustworthy and human-centered AI systems.

The project originated from exploratory prototyping during a Microsoft internal hackathon and continues as an independent open-source research and development effort. This research is being conducted independently outside the scope of my regular employment responsibilities at Microsoft, and future findings and tooling will be publicly released through GitHub and peer-reviewed publications.

请帮我写一个特别详细的markdown spec doc。
