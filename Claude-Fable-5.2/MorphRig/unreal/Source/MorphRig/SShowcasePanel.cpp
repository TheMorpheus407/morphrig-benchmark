#include "SShowcasePanel.h"
#include "MorphRigData.h"
#include "OperativeCharacter.h"
#include "OperativeStateComponent.h"
#include "ShowcaseDirector.h"
#include "ShowcasePlayerController.h"
#include "Styling/CoreStyle.h"
#include "Widgets/Input/SButton.h"
#include "Widgets/Input/SSearchBox.h"
#include "Widgets/Input/SSlider.h"
#include "Widgets/Layout/SBorder.h"
#include "Widgets/Layout/SBox.h"
#include "Widgets/Layout/SScrollBox.h"
#include "Widgets/Layout/SWidgetSwitcher.h"
#include "Widgets/Layout/SWrapBox.h"
#include "Widgets/SBoxPanel.h"
#include "Widgets/Text/STextBlock.h"
#include "Widgets/Views/STableRow.h"

namespace
{
	FSlateFontInfo PanelFont(int32 Size = 9, const TCHAR* Face = TEXT("Regular"))
	{
		return FCoreStyle::GetDefaultFontStyle(Face, Size);
	}
}

AShowcaseDirector* SShowcasePanel::Director() const
{
	return World.IsValid() ? AShowcaseDirector::Get(World.Get()) : nullptr;
}

UOperativeStateComponent* SShowcasePanel::State() const
{
	AShowcaseDirector* D = Director();
	AOperativeCharacter* Ch = D ? D->GetPrimary() : nullptr;
	return Ch ? Ch->StateComp.Get() : nullptr;
}

void SShowcasePanel::Run(const FString& Command) const
{
	if (AShowcaseDirector* D = Director())
	{
		D->Exec(Command);
	}
}

TSharedRef<SWidget> SShowcasePanel::Button(const FString& Label, const FString& Command, const FString& Tip)
{
	return SNew(SButton)
		.ContentPadding(FMargin(6.f, 2.f))
		.ButtonColorAndOpacity(FLinearColor(0.16f, 0.19f, 0.24f, 1.f))
		.ToolTipText(FText::FromString(Tip.IsEmpty() ? Command : Tip))
		.OnClicked_Lambda([this, Command]()
		{
			Run(Command);
			return FReply::Handled();
		})
		[
			SNew(STextBlock).Text(FText::FromString(Label)).Font(PanelFont(9)).ColorAndOpacity(FLinearColor(0.92f, 0.94f, 0.97f))
		];
}

TSharedRef<SWidget> SShowcasePanel::ButtonRow(const TArray<TPair<FString, FString>>& Items)
{
	TSharedRef<SWrapBox> Box = SNew(SWrapBox).UseAllottedSize(true).InnerSlotPadding(FVector2D(3.f, 3.f));
	for (const TPair<FString, FString>& It : Items)
	{
		Box->AddSlot()[Button(It.Key, It.Value)];
	}
	return Box;
}

TSharedRef<SWidget> SShowcasePanel::Header(const FString& Text)
{
	return SNew(SBox).Padding(FMargin(0.f, 7.f, 0.f, 2.f))
		[
			SNew(STextBlock).Text(FText::FromString(Text)).Font(PanelFont(10, TEXT("Bold"))).ColorAndOpacity(FLinearColor(0.55f, 0.85f, 1.0f))
		];
}

TSharedRef<SWidget> SShowcasePanel::SliderRow(const FString& Label, TFunction<float()> Getter, TFunction<void(float)> Setter, float Min, float Max)
{
	return SNew(SHorizontalBox)
		+ SHorizontalBox::Slot().AutoWidth().VAlign(VAlign_Center)
		[
			SNew(SBox).WidthOverride(138.f)
			[
				SNew(STextBlock).Text(FText::FromString(Label)).Font(PanelFont(8)).ColorAndOpacity(FLinearColor::White)
			]
		]
		+ SHorizontalBox::Slot().FillWidth(1.f).VAlign(VAlign_Center).Padding(4.f, 1.f)
		[
			SNew(SSlider)
			.MinValue(Min).MaxValue(Max)
			.Value_Lambda([Getter]() { return Getter(); })
			.OnValueChanged_Lambda([Setter](float V) { Setter(V); })
		]
		+ SHorizontalBox::Slot().AutoWidth().VAlign(VAlign_Center)
		[
			SNew(SBox).WidthOverride(40.f)
			[
				SNew(STextBlock).Font(PanelFont(8)).ColorAndOpacity(FLinearColor(0.8f, 0.8f, 0.8f))
				.Text_Lambda([Getter]() { return FText::FromString(FString::Printf(TEXT("%.2f"), Getter())); })
			]
		];
}

void SShowcasePanel::Construct(const FArguments& InArgs)
{
	World = InArgs._World;
	SetVisibility(EVisibility::SelfHitTestInvisible);
	static const TCHAR* TabNames[5] = { TEXT("Help"), TEXT("Animations"), TEXT("Face"), TEXT("Character"), TEXT("States") };
	TSharedRef<SHorizontalBox> Tabs = SNew(SHorizontalBox);
	for (int32 i = 0; i < 5; ++i)
	{
		Tabs->AddSlot().AutoWidth().Padding(1.f)
		[
			SNew(SButton).ContentPadding(FMargin(8.f, 3.f))
			.ButtonColorAndOpacity(FLinearColor(0.10f, 0.12f, 0.16f, 1.f))
			.OnClicked_Lambda([this, i]()
			{
				Tab = i;
				if (Switcher.IsValid())
				{
					Switcher->SetActiveWidgetIndex(i);
				}
				return FReply::Handled();
			})
			[
				SNew(STextBlock).Text(FText::FromString(TabNames[i])).Font(PanelFont(9, TEXT("Bold")))
				.ColorAndOpacity_Lambda([this, i]() { return Tab == i ? FSlateColor(FLinearColor(0.25f, 0.8f, 1.0f)) : FSlateColor(FLinearColor(0.85f, 0.87f, 0.9f)); })
			]
		];
	}
	ChildSlot
	.HAlign(HAlign_Right)
	.VAlign(VAlign_Top)
	.Padding(FMargin(0.f, 10.f, 10.f, 10.f))
	[
		SNew(SBox)
		.WidthOverride(452.f)
		.MaxDesiredHeight(980.f)
		.Visibility_Lambda([this]()
		{
			AShowcaseDirector* D = Director();
			return D && D->bShowPanel ? EVisibility::Visible : EVisibility::Collapsed;
		})
		[
			SNew(SBorder)
			.BorderImage(FCoreStyle::Get().GetBrush("GenericWhiteBox"))
			.BorderBackgroundColor(FLinearColor(0.015f, 0.018f, 0.024f, 0.86f))
			.Padding(8.f)
			[
				SNew(SVerticalBox)
				+ SVerticalBox::Slot().AutoHeight()[Tabs]
				+ SVerticalBox::Slot().FillHeight(1.f).Padding(0.f, 6.f, 0.f, 0.f)
				[
					SAssignNew(Switcher, SWidgetSwitcher)
					+ SWidgetSwitcher::Slot()[BuildHelp()]
					+ SWidgetSwitcher::Slot()[BuildAnimations()]
					+ SWidgetSwitcher::Slot()[BuildFace()]
					+ SWidgetSwitcher::Slot()[BuildCharacter()]
					+ SWidgetSwitcher::Slot()[BuildStates()]
				]
			]
		]
	];
}

void SShowcasePanel::SetTabByName(const FString& Name)
{
	const FString N = Name.ToLower();
	int32 Index = 0;
	if (N.StartsWith(TEXT("anim"))) { Index = 1; }
	else if (N.StartsWith(TEXT("face"))) { Index = 2; }
	else if (N.StartsWith(TEXT("char"))) { Index = 3; }
	else if (N.StartsWith(TEXT("state"))) { Index = 4; }
	Tab = Index;
	if (Switcher.IsValid())
	{
		Switcher->SetActiveWidgetIndex(Index);
	}
}

TSharedRef<SWidget> SShowcasePanel::BuildHelp()
{
	return SNew(SScrollBox)
		+ SScrollBox::Slot()
		[
			SNew(STextBlock).AutoWrapText(true).Font(PanelFont(8)).ColorAndOpacity(FLinearColor::White)
			.Text(FText::FromString(AShowcasePlayerController::HelpText()))
		]
		+ SScrollBox::Slot()[Header(TEXT("Quick actions"))]
		+ SScrollBox::Slot()
		[
			ButtonRow({ { TEXT("Run deterministic sequence"), TEXT("sequence") }, { TEXT("Stop script"), TEXT("stopscript") }, { TEXT("Reset character"), TEXT("reset") },
				{ TEXT("Play speech sample"), TEXT("speech") }, { TEXT("Help overlay"), TEXT("help toggle") } })
		];
}

void SShowcasePanel::RefreshClips()
{
	ClipItems.Reset();
	const FMorphRigData& Data = FMorphRigData::Get();
	const FString F = Filter.ToLower();
	for (const FMorphClip& C : Data.Clips)
	{
		const FString Hay = (C.Id.ToString() + TEXT(" ") + C.Form + TEXT(" ") + C.Layer.ToString()).ToLower();
		bool bMatch = true;
		TArray<FString> Terms;
		F.ParseIntoArrayWS(Terms);
		for (const FString& T : Terms)
		{
			bMatch &= Hay.Contains(T);
		}
		if (bMatch)
		{
			ClipItems.Add(MakeShared<FName>(C.Id));
		}
	}
	if (ClipList.IsValid())
	{
		ClipList->RequestListRefresh();
	}
}

TSharedRef<ITableRow> SShowcasePanel::MakeClipRow(TSharedPtr<FName> Item, const TSharedRef<STableViewBase>& Owner)
{
	const FMorphClip* C = FMorphRigData::Get().Find(*Item);
	const FString Text = C ? FString::Printf(TEXT("%-20s %-9s %-10s %5.2fs  %d ev"), *C->Id.ToString(), *C->Form, *C->Layer.ToString(), C->Duration, C->Events.Num()) : Item->ToString();
	return SNew(STableRow<TSharedPtr<FName>>, Owner)
		[
			SNew(STextBlock).Text(FText::FromString(Text)).Font(FCoreStyle::GetDefaultFontStyle("Mono", 8)).ColorAndOpacity(FLinearColor::White)
		];
}

TSharedRef<SWidget> SShowcasePanel::BuildAnimations()
{
	RefreshClips();
	return SNew(SVerticalBox)
		+ SVerticalBox::Slot().AutoHeight()
		[
			SNew(STextBlock).Font(PanelFont(8)).ColorAndOpacity(FLinearColor(0.8f, 0.8f, 0.8f)).AutoWrapText(true)
			.Text_Lambda([this]()
			{
				return FText::FromString(FString::Printf(TEXT("Motion viewer: %d of %d entries match. Type to filter by name, form or layer; click an entry to play it."),
					ClipItems.Num(), FMorphRigData::Get().Clips.Num()));
			})
		]
		+ SVerticalBox::Slot().AutoHeight().Padding(0.f, 4.f)
		[
			SNew(SSearchBox)
			.DelayChangeNotificationsWhileTyping(false)
			.HintText(FText::FromString(TEXT("search the 96 clips, e.g. walk, loop, aim, additive")))
			.OnTextChanged_Lambda([this](const FText& T)
			{
				Filter = T.ToString();
				RefreshClips();
			})
		]
		+ SVerticalBox::Slot().AutoHeight()
		[
			ButtonRow({ { TEXT("Play / pause"), TEXT("viewer toggle") }, { TEXT("Loop on/off"), TEXT("viewer loop toggle") }, { TEXT("Exit viewer"), TEXT("viewer exit") },
				{ TEXT("Go to dais"), TEXT("goto viewer") }, { TEXT("Front cam"), TEXT("cam front") }, { TEXT("Side cam"), TEXT("cam side") }, { TEXT("Skeleton"), TEXT("skeleton toggle") } })
		]
		+ SVerticalBox::Slot().AutoHeight()
		[
			SliderRow(TEXT("viewer rate"), [this]() { UOperativeStateComponent* S = State(); return S ? S->ViewerRate : 1.f; },
				[this](float V) { if (UOperativeStateComponent* S = State()) { S->ViewerRate = V; } }, 0.1f, 2.f)
		]
		+ SVerticalBox::Slot().AutoHeight()
		[
			SliderRow(TEXT("scrub (pauses)"), [this]()
				{
					UOperativeStateComponent* S = State();
					return S && S->GetBaseClip().IsValid() && S->GetBaseClip().Duration() > 0.f ? S->GetBaseClip().Time / S->GetBaseClip().Duration() : 0.f;
				},
				[this](float V) { if (UOperativeStateComponent* S = State()) { S->ViewerScrub(V); } })
		]
		+ SVerticalBox::Slot().FillHeight(1.f).Padding(0.f, 4.f, 0.f, 0.f)
		[
			SNew(SBox).MinDesiredHeight(480.f).MaxDesiredHeight(700.f)
			[
				SAssignNew(ClipList, SListView<TSharedPtr<FName>>)
				.ListItemsSource(&ClipItems)
				.SelectionMode(ESelectionMode::Single)
				.OnGenerateRow(this, &SShowcasePanel::MakeClipRow)
				.OnSelectionChanged_Lambda([this](TSharedPtr<FName> Item, ESelectInfo::Type)
				{
					if (Item.IsValid())
					{
						Run(FString::Printf(TEXT("view %s"), *Item->ToString()));
					}
				})
			]
		];
}

TSharedRef<SWidget> SShowcasePanel::BuildFace()
{
	const FMorphRigData& Data = FMorphRigData::Get();
	TSharedRef<SScrollBox> Box = SNew(SScrollBox);
	Box->AddSlot()
	[
		ButtonRow({ { TEXT("Reset face"), TEXT("face reset") }, { TEXT("Face camera"), TEXT("cam face") }, { TEXT("Head + shoulders"), TEXT("cam bust") }, { TEXT("Auto blink"), TEXT("autoblink toggle") },
			{ TEXT("Look at camera"), TEXT("lookcam toggle") }, { TEXT("Manual gaze off"), TEXT("gaze off") }, { TEXT("Speech sample"), TEXT("speech") } })
	];
	Box->AddSlot()[Header(TEXT("Gaze (independent eye look, lids follow)"))];
	Box->AddSlot()[SliderRow(TEXT("gaze yaw (left +)"), [this]() { UOperativeStateComponent* S = State(); return S ? S->GazeYawDeg : 0.f; },
		[this](float V) { if (UOperativeStateComponent* S = State()) { S->bManualGaze = true; S->GazeYawDeg = V; } }, -40.f, 40.f)];
	Box->AddSlot()[SliderRow(TEXT("gaze pitch (up +)"), [this]() { UOperativeStateComponent* S = State(); return S ? S->GazePitchDeg : 0.f; },
		[this](float V) { if (UOperativeStateComponent* S = State()) { S->bManualGaze = true; S->GazePitchDeg = V; } }, -35.f, 30.f)];
	Box->AddSlot()[Header(TEXT("Expression presets"))];
	for (const FName& N : Data.ExpressionNames)
	{
		Box->AddSlot()[SliderRow(N.ToString(), [this, N]() { UOperativeStateComponent* S = State(); return S ? S->FaceExpressions.FindRef(N) : 0.f; },
			[this, N](float V) { if (UOperativeStateComponent* S = State()) { S->FaceExpressions.Add(N, V); } })];
	}
	Box->AddSlot()[Header(TEXT("Visemes"))];
	for (const FName& N : Data.VisemeNames)
	{
		const FString* Note = Data.VisemeNotes.Find(N);
		Box->AddSlot()[SliderRow(FString::Printf(TEXT("%s  %s"), *N.ToString(), Note ? *Note->Left(18) : TEXT("")),
			[this, N]() { UOperativeStateComponent* S = State(); return S ? S->FaceVisemes.FindRef(N) : 0.f; },
			[this, N](float V) { if (UOperativeStateComponent* S = State()) { S->FaceVisemes.Add(N, V); } })];
	}
	Box->AddSlot()[Header(TEXT("Individual controls (left / right separately)"))];
	for (const FName& N : Data.Controls)
	{
		Box->AddSlot()[SliderRow(N.ToString(), [this, N]() { UOperativeStateComponent* S = State(); return S ? S->FaceDirect.FindRef(N) : 0.f; },
			[this, N](float V) { if (UOperativeStateComponent* S = State()) { S->FaceDirect.Add(N, V); } })];
	}
	return Box;
}

TSharedRef<SWidget> SShowcasePanel::BuildCharacter()
{
	return SNew(SScrollBox)
		+ SScrollBox::Slot()[Header(TEXT("Team accent (colour + icon; outline and ring are colour independent cues)"))]
		+ SScrollBox::Slot()[ButtonRow({ { TEXT("Team A"), TEXT("team A") }, { TEXT("Team B"), TEXT("team B") }, { TEXT("Outline on/off"), TEXT("outline toggle") },
			{ TEXT("Ground ring on/off"), TEXT("ring toggle") } })]
		+ SScrollBox::Slot()[Header(TEXT("LOD"))]
		+ SScrollBox::Slot()[ButtonRow({ { TEXT("Auto"), TEXT("lod auto") }, { TEXT("LOD0"), TEXT("lod 0") }, { TEXT("LOD1"), TEXT("lod 1") }, { TEXT("LOD2"), TEXT("lod 2") } })]
		+ SScrollBox::Slot()[Header(TEXT("Display"))]
		+ SScrollBox::Slot()[ButtonRow({ { TEXT("Textured"), TEXT("display textured") }, { TEXT("Wireframe mesh"), TEXT("display wireframe") },
			{ TEXT("Normals"), TEXT("display normals") }, { TEXT("Clay"), TEXT("display clay") }, { TEXT("Skeleton overlay"), TEXT("skeleton toggle") }, { TEXT("HUD"), TEXT("hud toggle") } })]
		+ SScrollBox::Slot()[Header(TEXT("Camera"))]
		+ SScrollBox::Slot()[ButtonRow({ { TEXT("Top-down"), TEXT("cam top") }, { TEXT("Third person"), TEXT("cam third") }, { TEXT("Front"), TEXT("cam front") },
			{ TEXT("Side"), TEXT("cam side") }, { TEXT("Face close-up"), TEXT("cam face") }, { TEXT("Head + shoulders"), TEXT("cam bust") }, { TEXT("Orbit"), TEXT("cam orbit") }, { TEXT("Turntable"), TEXT("cam turntable") } })]
		+ SScrollBox::Slot()[Header(TEXT("Instances"))]
		+ SScrollBox::Slot()[ButtonRow({ { TEXT("1 Operative"), TEXT("instances 1") }, { TEXT("10 Operatives"), TEXT("instances 10") } })]
		+ SScrollBox::Slot()[Header(TEXT("Locomotion"))]
		+ SScrollBox::Slot()[ButtonRow({ { TEXT("Strafe / travel mode"), TEXT("strafe toggle") }, { TEXT("Wounded"), TEXT("wounded toggle") }, { TEXT("Turn left 90"), TEXT("turn l") },
			{ TEXT("Turn right 90"), TEXT("turn r") }, { TEXT("To ramp"), TEXT("goto ramp") }, { TEXT("To steps"), TEXT("goto steps") }, { TEXT("To station"), TEXT("goto station") },
			{ TEXT("To spawn"), TEXT("goto spawn") } })]
		+ SScrollBox::Slot()[SliderRow(TEXT("speed limit cm/s"), [this]() { AShowcaseDirector* D = Director(); return D && D->ScriptSpeed >= 0.f ? D->ScriptSpeed : 650.f; },
			[this](float V) { if (AShowcaseDirector* D = Director()) { D->ScriptSpeed = V >= 649.f ? -1.f : V; } }, 0.f, 650.f)]
		+ SScrollBox::Slot()[SliderRow(TEXT("action rate"), [this]() { UOperativeStateComponent* S = State(); return S ? S->ActionRate : 1.f; },
			[this](float V) { if (UOperativeStateComponent* S = State()) { S->ActionRate = FMath::Clamp(V, 0.5f, 1.5f); } }, 0.5f, 1.5f)]
		+ SScrollBox::Slot()[Header(TEXT("Procedural layers"))]
		+ SScrollBox::Slot()[ButtonRow({ { TEXT("Foot IK"), TEXT("footik toggle") }, { TEXT("Cable simulation"), TEXT("secondary toggle") },
			{ TEXT("Twist / helper bones"), TEXT("helpers toggle") }, { TEXT("Look-at"), TEXT("lookat toggle") } })]
		+ SScrollBox::Slot()
		[
			SNew(STextBlock).Font(PanelFont(8)).ColorAndOpacity(FLinearColor(0.8f, 0.8f, 0.8f)).AutoWrapText(true)
			.Text_Lambda([this]()
			{
				UOperativeStateComponent* S = State();
				if (!S)
				{
					return FText::GetEmpty();
				}
				return FText::FromString(FString::Printf(TEXT("foot IK %s | cable sim %s | helpers %s | look-at %s | %s"), S->bFootIK ? TEXT("on") : TEXT("off"),
					S->bSimulateSecondary ? TEXT("on") : TEXT("off"), S->bProceduralBones ? TEXT("on") : TEXT("off"), S->bLookAt ? TEXT("on") : TEXT("off"),
					S->bStrafe ? TEXT("strafe mode") : TEXT("travel mode")));
			})
		];
}

TSharedRef<SWidget> SShowcasePanel::BuildStates()
{
	return SNew(SScrollBox)
		+ SScrollBox::Slot()[Header(TEXT("Movement actions"))]
		+ SScrollBox::Slot()[ButtonRow({ { TEXT("Jump"), TEXT("jump") }, { TEXT("Long fall"), TEXT("drop") }, { TEXT("Dash F"), TEXT("dash f") }, { TEXT("Dash B"), TEXT("dash b") },
			{ TEXT("Dash L"), TEXT("dash l") }, { TEXT("Dash R"), TEXT("dash r") }, { TEXT("Blink forward"), TEXT("blink") } })]
		+ SScrollBox::Slot()[Header(TEXT("Attacks and casts"))]
		+ SScrollBox::Slot()[ButtonRow({ { TEXT("Melee (combo)"), TEXT("melee") }, { TEXT("Fire"), TEXT("fire") }, { TEXT("Burst"), TEXT("burst") }, { TEXT("Reload"), TEXT("reload") },
			{ TEXT("Cast directional"), TEXT("cast directional") }, { TEXT("Cast ground"), TEXT("cast ground") }, { TEXT("Cast self"), TEXT("cast self") }, { TEXT("Deploy beacon"), TEXT("deploy") } })]
		+ SScrollBox::Slot()[Header(TEXT("Channel / charge / uplink (start, finish or interrupt at any point)"))]
		+ SScrollBox::Slot()[ButtonRow({ { TEXT("Channel start"), TEXT("channel start") }, { TEXT("Channel finish"), TEXT("channel release") }, { TEXT("Channel INTERRUPT"), TEXT("channel interrupt") },
			{ TEXT("Charge start"), TEXT("charge start") }, { TEXT("Charge release"), TEXT("charge release") }, { TEXT("Charge cancel"), TEXT("charge cancel") },
			{ TEXT("Uplink start"), TEXT("uplink start") }, { TEXT("Uplink cancel"), TEXT("uplink cancel") } })]
		+ SScrollBox::Slot()[Header(TEXT("Hits (additive) and disables"))]
		+ SScrollBox::Slot()[ButtonRow({ { TEXT("Hit front"), TEXT("hit f") }, { TEXT("Hit left"), TEXT("hit l") }, { TEXT("Hit back"), TEXT("hit b") }, { TEXT("Hit right"), TEXT("hit r") },
			{ TEXT("Heavy hit"), TEXT("hit f heavy") }, { TEXT("Stun 2s"), TEXT("stun 2") }, { TEXT("Sleep 5s"), TEXT("sleep 5") }, { TEXT("Knock-back"), TEXT("knockback f") },
			{ TEXT("Knock-up"), TEXT("knockup") }, { TEXT("Knock-down (front hit)"), TEXT("knockdown front") }, { TEXT("Knock-down (back hit)"), TEXT("knockdown back") } })]
		+ SScrollBox::Slot()[Header(TEXT("Status flags"))]
		+ SScrollBox::Slot()[ButtonRow({ { TEXT("Root"), TEXT("flag root toggle") }, { TEXT("Silence"), TEXT("flag silence toggle") }, { TEXT("Disarm"), TEXT("flag disarm toggle") },
			{ TEXT("Stasis"), TEXT("flag stasis toggle") }, { TEXT("Fear"), TEXT("flag fear toggle") }, { TEXT("Charm"), TEXT("flag charm toggle") }, { TEXT("Taunt"), TEXT("flag taunt toggle") },
			{ TEXT("Wounded"), TEXT("wounded toggle") } })]
		+ SScrollBox::Slot()[Header(TEXT("Death / respawn"))]
		+ SScrollBox::Slot()[ButtonRow({ { TEXT("Death (front hit)"), TEXT("kill front") }, { TEXT("Death (back hit)"), TEXT("kill back") }, { TEXT("Respawn"), TEXT("respawn") },
			{ TEXT("Reset character"), TEXT("reset") } })]
		+ SScrollBox::Slot()[Header(TEXT("Emotes and speech"))]
		+ SScrollBox::Slot()[ButtonRow({ { TEXT("Greet"), TEXT("emote greet") }, { TEXT("Victory"), TEXT("emote victory") }, { TEXT("Defeat"), TEXT("emote defeat") },
			{ TEXT("Speech sample"), TEXT("speech") } })]
		+ SScrollBox::Slot()[Header(TEXT("Showcase"))]
		+ SScrollBox::Slot()[ButtonRow({ { TEXT("Run deterministic sequence"), TEXT("sequence") }, { TEXT("Stop script"), TEXT("stopscript") } })];
}
