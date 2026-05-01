from dataclasses import asdict, dataclass


@dataclass
class Author:
    handle: str | None
    name: str | None
    avatar: str | None
    followers: int | None
    tags: list[str]


@dataclass
class Media:
    type: str | None
    url: str | None


@dataclass
class Content:
    text: str | None
    media: list[Media]


@dataclass
class Reference:
    tweet_id: str | None
    author_handle: str | None
    author_name: str | None
    author_avatar: str | None
    author_followers: int | None
    text: str | None
    media: list[Media]
    type: str


@dataclass
class UnfollowTarget:
    handle: str | None
    name: str | None
    bio: str | None
    avatar: str | None
    followers: int | None


@dataclass
class AvatarChange:
    before: str | None
    after: str | None


@dataclass
class BioChange:
    before: str | None
    after: str | None


@dataclass
class StandardizedMessage:
    action: str
    original_action: str | None
    tweet_id: str | None
    internal_id: str | None
    timestamp: int
    author: Author
    content: Content
    reference: Reference | None
    unfollow_target: UnfollowTarget | None
    avatar_change: AvatarChange | None
    bio_change: BioChange | None

    def to_dict(self) -> dict:
        return asdict(self)
