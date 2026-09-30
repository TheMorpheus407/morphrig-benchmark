#include "ShowcasePanel.h"
#include "ShowcasePlayerController.h"
#include "ShowcaseRoom.h"
#include "ShowcaseDirector.h"
#include "OperativeActionComponent.h"
#include "OperativeFaceComponent.h"
#include "OperativeLibrary.h"
#include "Framework/Application/SlateApplication.h"
#include "Styling/CoreStyle.h"
#include "Widgets/Input/SButton.h"
#include "Widgets/Input/SCheckBox.h"
#include "Widgets/Input/SSlider.h"
#include "Widgets/Input/SEditableTextBox.h"
#include "Widgets/Layout/SBorder.h"
#include "Widgets/Layout/SBox.h"
#include "Widgets/Layout/SScrollBox.h"
#include "Widgets/Layout/SExpandableArea.h"
#include "Widgets/Layout/SUniformGridPanel.h"
#include "Widgets/Layout/SWrapBox.h"
#include "Widgets/Text/STextBlock.h"
#include "Widgets/SBoxPanel.h"
#include "Widgets/Views/STableRow.h"
#include "Widgets/Views/SListView.h"

namespace
{
	FSlateFontInfo PanelFont(int32 Size = 9) { return FCoreStyle::GetDefaultFontStyle("Regular", Size); }

	void ReturnFocus()
	{
		if (FSlateApplication::IsInitialized()) FSlateApplication::Get().SetUserFocusToGameViewport(0);
	}

	TSharedRef<SWidget> Btn(const FString& Label, TFunction<void()> Fn, const FString& Tip = FString())
	{
		return SNew(SButton)
			.ContentPadding(FMargin(5.f, 2.f))
			.ToolTipText(FText::FromString(Tip))
			.OnClicked_Lambda([Fn]() { if (Fn) Fn(); ReturnFocus(); return FReply::Handled(); })
			[
				SNew(STextBlock).Text(FText::FromString(Label)).Font(PanelFont(9))
			];
	}

	TSharedRef<SWidget> Toggle(const FString& Label, TFunction<bool()> Get, TFunction<void(bool)> Set)
	{
		return SNew(SCheckBox)
			.IsChecked_Lambda([Get]() { return (Get && Get()) ? ECheckBoxState::Checked : ECheckBoxState::Unchecked; })
			.OnCheckStateChanged_Lambda([Set](ECheckBoxState S) { if (Set) Set(S == ECheckBoxState::Checked); ReturnFocus(); })
			[
				SNew(STextBlock).Text(FText::FromString(Label)).Font(PanelFont(9))
			];
	}

	TSharedRef<SWidget> Slide(const FString& Label, float Min, float Max, TFunction<float()> Get, TFunction<void(float)> Set, int32 LabelWidth = 110)
	{
		return SNew(SHorizontalBox)
			+ SHorizontalBox::Slot().AutoWidth().VAlign(VAlign_Center)
			[
				SNew(SBox).WidthOverride(LabelWidth)[SNew(STextBlock).Text(FText::FromString(Label)).Font(PanelFont(8))]
			]
			+ SHorizontalBox::Slot().FillWidth(1.f).VAlign(VAlign_Center).Padding(2.f, 0.f)
			[
				SNew(SSlider)
				.Value_Lambda([Get, Min, Max]() { return Max > Min ? (Get() - Min) / (Max - Min) : 0.f; })
				.OnValueChanged_Lambda([Set, Min, Max](float V) { if (Set) Set(Min + V * (Max - Min)); })
			]
			+ SHorizontalBox::Slot().AutoWidth().VAlign(VAlign_Center)
			[
				SNew(SBox).WidthOverride(46)[SNew(STextBlock).Text_Lambda([Get]() { return FText::FromString(FString::Printf(TEXT("%.2f"), Get())); }).Font(PanelFont(8))]
			];
	}

	TSharedRef<SWidget> Section(const FString& Title, TSharedRef<SWidget> Body, bool bCollapsed)
	{
		return SNew(SExpandableArea)
			.AreaTitle(FText::FromString(Title))
			.InitiallyCollapsed(bCollapsed)
			.BodyContent()[Body];
	}

	TSharedRef<SWidget> Wrap(const TArray<TSharedRef<SWidget>>& Items)
	{
		TSharedRef<SWrapBox> Box = SNew(SWrapBox).UseAllottedSize(true).InnerSlotPadding(FVector2D(3.f, 3.f));
		for (const TSharedRef<SWidget>& W : Items) Box->AddSlot()[W];
		return Box;
	}

	FText TextOf(const FString& S) { return FText::FromString(S); }
}

void SShowcasePanel::Construct(const FArguments& InArgs)
{
	Ctrl = InArgs._Controller;
	if (const UOperativeLibrary* Lib = UOperativeLibrary::Get(Ctrl.Get()))
	{
		for (const FName& Id : Lib->GetClipOrder()) AllClips.Add(MakeShared<FName>(Id));
	}
	FilteredClips = AllClips;

	ChildSlot
	[
		SNew(SBox).WidthOverride(370.f).HAlign(HAlign_Left)
		[
			SNew(SBorder)
			.BorderImage(FCoreStyle::Get().GetBrush("GenericWhiteBox"))
			.BorderBackgroundColor(FLinearColor(0.02f, 0.025f, 0.035f, 0.86f))
			.Padding(6.f)
			.Visibility(EVisibility::Visible)
			[
				SNew(SScrollBox)
				+ SScrollBox::Slot()
				[
					SNew(STextBlock).Text(TextOf(TEXT("MORPHRIG  Operative showcase   (F1 help, F2 hide panel)"))).Font(PanelFont(11)).ColorAndOpacity(FLinearColor(0.4f, 0.9f, 1.f))
				]
				+ SScrollBox::Slot().Padding(0.f, 4.f) [Section(TEXT("View, render, team, LOD, instances"), BuildViewSection(), false)]
				+ SScrollBox::Slot().Padding(0.f, 4.f) [Section(TEXT("Locomotion, aim, stance"), BuildLocomotionSection(), false)]
				+ SScrollBox::Slot().Padding(0.f, 4.f) [Section(TEXT("Actions"), BuildActionSection(), false)]
				+ SScrollBox::Slot().Padding(0.f, 4.f) [Section(TEXT("Hits, disables, death"), BuildHitSection(), false)]
				+ SScrollBox::Slot().Padding(0.f, 4.f) [Section(TEXT("Animation browser (96 clips)"), BuildBrowserSection(), false)]
				+ SScrollBox::Slot().Padding(0.f, 4.f) [Section(TEXT("Face control panel"), BuildFaceSection(), true)]
			]
		]
	];
}

TSharedRef<SWidget> SShowcasePanel::BuildViewSection()
{
	AShowcasePlayerController* C = Ctrl.Get();
	TArray<TSharedRef<SWidget>> Views = {
		Btn(TEXT("Third person"), [C]() { C->SetView(EShowcaseView::ThirdPerson); }, TEXT("Home")),
		Btn(TEXT("Front"), [C]() { C->SetView(EShowcaseView::Front); }, TEXT("PageUp")),
		Btn(TEXT("Side"), [C]() { C->SetView(EShowcaseView::Side); }, TEXT("PageDown")),
		Btn(TEXT("Top-down"), [C]() { C->SetView(EShowcaseView::TopDown); }, TEXT("End")),
		Btn(TEXT("Face"), [C]() { C->SetView(EShowcaseView::Face); }, TEXT("Insert")),
		Btn(TEXT("Hands"), [C]() { C->SetView(EShowcaseView::Hands); }, TEXT("Delete")) };
	TArray<TSharedRef<SWidget>> Render = {
		Btn(TEXT("Textured"), [C]() { C->SetRenderMode(0); }),
		Btn(TEXT("Normals"), [C]() { C->SetRenderMode(1); }),
		Btn(TEXT("Wireframe"), [C]() { C->SetRenderMode(2); }),
		Btn(TEXT("Clay mesh"), [C]() { C->SetRenderMode(3); }) };
	TArray<TSharedRef<SWidget>> Lod = {
		Btn(TEXT("LOD auto"), [C]() { C->SetLOD(0); }),
		Btn(TEXT("LOD0"), [C]() { C->SetLOD(1); }),
		Btn(TEXT("LOD1"), [C]() { C->SetLOD(2); }),
		Btn(TEXT("LOD2"), [C]() { C->SetLOD(3); }) };
	TArray<TSharedRef<SWidget>> Team = {
		Btn(TEXT("Team A (cyan, circle)"), [C]() { C->SetTeam(EOperativeTeam::A); }),
		Btn(TEXT("Team B (magenta, diamond)"), [C]() { C->SetTeam(EOperativeTeam::B); }),
		Toggle(TEXT("outline"), [C]() { AOperativeCharacter* O = C->GetOperative(); return O && O->IsOutlineEnabled(); }, [C](bool) { C->ToggleOutline(); }),
		Toggle(TEXT("studio backdrop"), [C]() { return C->IsStudio(); }, [C](bool) { C->ToggleStudio(); }) };
	TArray<TSharedRef<SWidget>> Overlay = {
		Btn(TEXT("Overlays off"), [C]() { C->SetOverlayMode(0); }),
		Btn(TEXT("Skeleton"), [C]() { C->SetOverlayMode(1); }),
		Btn(TEXT("Sockets + IK + rays"), [C]() { C->SetOverlayMode(2); }),
		Btn(TEXT("All + labels"), [C]() { C->SetOverlayMode(3); }) };
	TArray<TSharedRef<SWidget>> Misc = {
		Btn(TEXT("1 Operative"), [C]() { C->SetInstances(1); }),
		Btn(TEXT("10 Operatives"), [C]() { C->SetInstances(10); }),
		Btn(TEXT("Run showcase sequence"), [C]() { C->StartSequence(); }, TEXT("F8")),
		Toggle(TEXT("targets patrol"), [C]() { AShowcaseRoom* R = C->GetRoom(); return R && R->GetTargetsPatrol(); }, [C](bool) { C->ToggleTargetsPatrol(); }),
		Btn(TEXT("Next target"), [C]() { C->SelectNextTarget(); }, TEXT(",")),
		Btn(TEXT("Move target to cursor"), [C]() { C->MoveSelectedTargetToCursor(); }, TEXT(".")),
		Btn(TEXT("Help"), [C]() { C->ToggleHelp(); }, TEXT("F1")) };
	return SNew(SVerticalBox)
		+ SVerticalBox::Slot().AutoHeight().Padding(0, 2)[Wrap(Views)]
		+ SVerticalBox::Slot().AutoHeight().Padding(0, 2)[Wrap(Render)]
		+ SVerticalBox::Slot().AutoHeight().Padding(0, 2)[Wrap(Lod)]
		+ SVerticalBox::Slot().AutoHeight().Padding(0, 2)[Wrap(Team)]
		+ SVerticalBox::Slot().AutoHeight().Padding(0, 2)[Wrap(Overlay)]
		+ SVerticalBox::Slot().AutoHeight().Padding(0, 2)[Wrap(Misc)]
		+ SVerticalBox::Slot().AutoHeight().Padding(0, 2)[SNew(STextBlock).Font(PanelFont(8)).Text_Lambda([C]() {
			return TextOf(FString::Printf(TEXT("view %s | render %s | LOD %d | instances %d | char %.0f px"), *C->GetViewName(), *C->GetRenderModeName(),
				C->GetOperative() ? C->GetOperative()->GetForcedLOD() - 1 : 0, C->GetInstanceCount(), C->GetCharacterPixelHeight())); })];
}

TSharedRef<SWidget> SShowcasePanel::BuildLocomotionSection()
{
	AShowcasePlayerController* C = Ctrl.Get();
	TArray<TSharedRef<SWidget>> Gait = {
		Btn(TEXT("Walk 150"), [C]() { C->SetGait(EOperativeGait::Walk); }),
		Btn(TEXT("Run 400"), [C]() { C->SetGait(EOperativeGait::Run); }),
		Btn(TEXT("Sprint 650"), [C]() { C->SetGait(EOperativeGait::Sprint); }),
		Btn(TEXT("Facing: aim"), [C]() { C->SetFacingMode(EOperativeFacingMode::Aim); }),
		Btn(TEXT("Facing: movement"), [C]() { C->SetFacingMode(EOperativeFacingMode::Movement); }),
		Btn(TEXT("Facing: locked"), [C]() { C->SetFacingMode(EOperativeFacingMode::Locked); }) };
	auto Dir = [C](float Angle, const TCHAR* Name) { return Btn(Name, [C, Angle]() { C->SetManualLocomotion(true, Angle, C->GetManualSpeed() > 5.f ? C->GetManualSpeed() : 400.f); }); };
	TArray<TSharedRef<SWidget>> Dirs = {
		Dir(0.f, TEXT("F")), Dir(45.f, TEXT("FL")), Dir(90.f, TEXT("L")), Dir(135.f, TEXT("BL")),
		Dir(180.f, TEXT("B")), Dir(-135.f, TEXT("BR")), Dir(-90.f, TEXT("R")), Dir(-45.f, TEXT("FR")),
		Btn(TEXT("Stop"), [C]() { C->SetManualLocomotion(true, C->GetManualAngle(), 0.f); }),
		Btn(TEXT("Keyboard"), [C]() { C->SetManualLocomotion(false, 0.f, 0.f); }) };
	TArray<TSharedRef<SWidget>> Stance = {
		Toggle(TEXT("aim pose (hold)"), [C]() { return C->GetAimToggle(); }, [C](bool B) { C->SetAimToggle(B); }),
		Toggle(TEXT("combat stance"), [C]() { return false; }, [C](bool B) { if (auto* A = C->GetActions()) A->SetCombatStance(B); }),
		Toggle(TEXT("wounded"), [C]() { return false; }, [C](bool B) { if (auto* A = C->GetActions()) A->SetWoundedOverride(B); }),
		Toggle(TEXT("always aim"), [C]() { auto* A = C->GetActions(); return A && A->GetAimAlways(); }, [C](bool B) { if (auto* A = C->GetActions()) A->SetAimAlways(B); }),
		Toggle(TEXT("foot IK"), [C]() { return true; }, [C](bool B) { if (auto* A = C->GetActions()) A->SetIKEnabled(B); }),
		Toggle(TEXT("secondary motion"), [C]() { return true; }, [C](bool B) { if (auto* A = C->GetActions()) A->SetSecondaryEnabled(B); }) };
	return SNew(SVerticalBox)
		+ SVerticalBox::Slot().AutoHeight().Padding(0, 2)[Wrap(Gait)]
		+ SVerticalBox::Slot().AutoHeight().Padding(0, 2)[SNew(STextBlock).Font(PanelFont(8)).Text(TextOf(TEXT("Direction relative to the body (drives the 8 direction gait blend):")))]
		+ SVerticalBox::Slot().AutoHeight().Padding(0, 2)[Wrap(Dirs)]
		+ SVerticalBox::Slot().AutoHeight()[Slide(TEXT("speed cm/s"), 0.f, 650.f, [C]() { return C->GetManualSpeed(); }, [C](float V) { C->SetManualLocomotion(true, C->GetManualAngle(), V); })]
		+ SVerticalBox::Slot().AutoHeight().Padding(0, 4)[Toggle(TEXT("manual aim (sliders)"), [C]() { return C->IsManualAim(); }, [C](bool B) { C->SetManualAim(B, 0.f, 0.f); })]
		+ SVerticalBox::Slot().AutoHeight()[Slide(TEXT("aim yaw (left +)"), -60.f, 60.f, [C]() { AOperativeCharacter* O = C->GetOperative(); return O && O->Actions ? O->Actions->GetAimYaw() : 0.f; }, [C](float V) { C->SetManualAim(true, V, C->GetOperative() ? C->GetOperative()->Actions->GetAimPitch() : 0.f); })]
		+ SVerticalBox::Slot().AutoHeight()[Slide(TEXT("aim pitch (up +)"), -35.f, 35.f, [C]() { AOperativeCharacter* O = C->GetOperative(); return O && O->Actions ? O->Actions->GetAimPitch() : 0.f; }, [C](float V) { C->SetManualAim(true, C->GetOperative() ? C->GetOperative()->Actions->GetAimYaw() : 0.f, V); })]
		+ SVerticalBox::Slot().AutoHeight().Padding(0, 4)[Wrap(Stance)]
		+ SVerticalBox::Slot().AutoHeight()[Slide(TEXT("action rate"), 0.5f, 1.5f, [C]() { auto* A = C->GetActions(); return A ? A->GetActionRate() : 1.f; }, [C](float V) { C->SetActionRate(V); })]
		+ SVerticalBox::Slot().AutoHeight()[Slide(TEXT("health"), 0.f, 1.f, [C]() { auto* A = C->GetActions(); return A ? A->GetHealthFraction() : 1.f; }, [C](float V) { if (auto* A = C->GetActions()) A->SetHealthFraction(V); })];
}

TSharedRef<SWidget> SShowcasePanel::BuildActionSection()
{
	AShowcasePlayerController* C = Ctrl.Get();
	TArray<TSharedRef<SWidget>> A = {
		Btn(TEXT("Jump"), [C]() { C->CmdJump(); }, TEXT("Space")),
		Btn(TEXT("Dash"), [C]() { C->CmdDash(); }, TEXT("V")),
		Btn(TEXT("Blink"), [C]() { C->CmdBlink(); }, TEXT("B")),
		Btn(TEXT("Fire"), [C]() { C->CmdFire(); }, TEXT("LMB")),
		Btn(TEXT("Burst"), [C]() { C->CmdBurst(); }, TEXT("F")),
		Btn(TEXT("Melee (chain)"), [C]() { C->CmdMelee(); }, TEXT("E")),
		Btn(TEXT("Reload"), [C]() { C->CmdReload(); }, TEXT("R")),
		Btn(TEXT("Cast directional"), [C]() { C->CmdCastDirectional(); }, TEXT("1")),
		Btn(TEXT("Cast ground"), [C]() { C->CmdCastGround(); }, TEXT("2")),
		Btn(TEXT("Cast self"), [C]() { C->CmdCastSelf(); }, TEXT("3")),
		Btn(TEXT("Channel start"), [C]() { C->CmdChannelPressed(); }, TEXT("4")),
		Btn(TEXT("Channel release"), [C]() { C->CmdChannelReleased(); }),
		Btn(TEXT("Charge start"), [C]() { C->CmdChargePressed(); }, TEXT("5")),
		Btn(TEXT("Charge release"), [C]() { C->CmdChargeReleased(); }),
		Btn(TEXT("Charge cancel"), [C]() { C->CmdChargeCancel(); }, TEXT("C")),
		Btn(TEXT("Deploy beacon"), [C]() { C->CmdDeploy(); }, TEXT("6")),
		Btn(TEXT("Uplink start / cancel"), [C]() { C->CmdUplink(); }, TEXT("7")),
		Btn(TEXT("Interrupt"), [C]() { C->CmdInterrupt(); }, TEXT("X")),
		Btn(TEXT("Greet"), [C]() { C->CmdGreet(); }, TEXT("G")),
		Btn(TEXT("Victory"), [C]() { C->CmdVictory(); }, TEXT("H")),
		Btn(TEXT("Defeat"), [C]() { C->CmdDefeat(); }, TEXT("O")),
		Btn(TEXT("Speech sample"), [C]() { C->CmdDialogue(); }, TEXT("P / Enter")) };
	return Wrap(A);
}

TSharedRef<SWidget> SShowcasePanel::BuildHitSection()
{
	AShowcasePlayerController* C = Ctrl.Get();
	TArray<TSharedRef<SWidget>> H = {
		Btn(TEXT("Hit front"), [C]() { C->CmdHit(0); }, TEXT("Up")),
		Btn(TEXT("Hit back"), [C]() { C->CmdHit(1); }, TEXT("Down")),
		Btn(TEXT("Hit left"), [C]() { C->CmdHit(2); }, TEXT("Left")),
		Btn(TEXT("Hit right"), [C]() { C->CmdHit(3); }, TEXT("Right")),
		Btn(TEXT("Stun 2 s"), [C]() { C->CmdStun(); }, TEXT("T")),
		Btn(TEXT("Sleep / wake"), [C]() { C->CmdSleepToggle(); }, TEXT("Y")),
		Btn(TEXT("Knockback"), [C]() { C->CmdKnockback(); }, TEXT("N")),
		Btn(TEXT("Knockup"), [C]() { C->CmdKnockup(); }, TEXT("U")),
		Btn(TEXT("Knockdown (front hit)"), [C]() { C->CmdKnockdown(true); }, TEXT("J")),
		Btn(TEXT("Knockdown (back hit)"), [C]() { C->CmdKnockdown(false); }, TEXT("Z")),
		Btn(TEXT("Kill (front hit)"), [C]() { if (auto* A = C->GetActions()) A->Kill(-C->GetOperative()->GetActorForwardVector()); }, TEXT("K")),
		Btn(TEXT("Kill (back hit)"), [C]() { if (auto* A = C->GetActions()) A->Kill(C->GetOperative()->GetActorForwardVector()); }),
		Btn(TEXT("Respawn"), [C]() { C->CmdRespawn(); }, TEXT("L")),
		Btn(TEXT("Reset character"), [C]() { C->CmdReset(); }, TEXT("Backspace")),
		Toggle(TEXT("root"), [C]() { auto* A = C->GetActions(); return A && A->IsRooted(); }, [C](bool) { C->CmdToggleRoot(); }),
		Toggle(TEXT("silence"), [C]() { auto* A = C->GetActions(); return A && A->IsSilenced(); }, [C](bool) { C->CmdToggleSilence(); }),
		Toggle(TEXT("disarm"), [C]() { auto* A = C->GetActions(); return A && A->IsDisarmed(); }, [C](bool) { C->CmdToggleDisarm(); }),
		Toggle(TEXT("stasis"), [C]() { auto* A = C->GetActions(); return A && A->IsStasis(); }, [C](bool) { C->CmdToggleStasis(); }) };
	return Wrap(H);
}

void SShowcasePanel::RebuildFilter()
{
	FilteredClips.Reset();
	const UOperativeLibrary* Lib = UOperativeLibrary::Get(Ctrl.Get());
	for (const TSharedPtr<FName>& Item : AllClips)
	{
		bool bMatch = SearchText.IsEmpty() || Item->ToString().Contains(SearchText, ESearchCase::IgnoreCase);
		if (!bMatch && Lib)
		{
			if (const FOperativeClipInfo* Info = Lib->FindClip(*Item)) bMatch = Info->Form.Contains(SearchText, ESearchCase::IgnoreCase) || Info->Behavior.Contains(SearchText, ESearchCase::IgnoreCase);
		}
		if (bMatch) FilteredClips.Add(Item);
	}
	if (ClipList.IsValid()) ClipList->RequestListRefresh();
}

TSharedRef<ITableRow> SShowcasePanel::GenerateClipRow(TSharedPtr<FName> Item, const TSharedRef<STableViewBase>& Owner)
{
	const UOperativeLibrary* Lib = UOperativeLibrary::Get(Ctrl.Get());
	FString Info = TEXT("");
	if (Lib)
	{
		if (const FOperativeClipInfo* C = Lib->FindClip(*Item))
		{
			Info = FString::Printf(TEXT("%s  %.2fs%s"), *C->Form, C->Length(), C->Events.Num() > 0 ? *FString::Printf(TEXT("  %d ev"), C->Events.Num()) : TEXT(""));
		}
	}
	return SNew(STableRow<TSharedPtr<FName>>, Owner)
	[
		SNew(SHorizontalBox)
		+ SHorizontalBox::Slot().FillWidth(1.f)[SNew(STextBlock).Text(TextOf(Item->ToString())).Font(PanelFont(9))]
		+ SHorizontalBox::Slot().AutoWidth()[SNew(STextBlock).Text(TextOf(Info)).Font(PanelFont(8)).ColorAndOpacity(FLinearColor(0.6f, 0.7f, 0.8f))]
	];
}

TSharedRef<SWidget> SShowcasePanel::BuildBrowserSection()
{
	AShowcasePlayerController* C = Ctrl.Get();
	SAssignNew(ClipList, SListView<TSharedPtr<FName>>)
		.ListItemsSource(&FilteredClips)
		.OnGenerateRow(this, &SShowcasePanel::GenerateClipRow)
		.SelectionMode(ESelectionMode::Single)
		.OnSelectionChanged_Lambda([C](TSharedPtr<FName> Item, ESelectInfo::Type) { if (Item.IsValid() && C) C->BrowserPlay(*Item); });
	return SNew(SVerticalBox)
		+ SVerticalBox::Slot().AutoHeight()
		[
			SNew(SEditableTextBox)
			.HintText(TextOf(TEXT("search clips (id, form, behavior)")))
			.OnTextChanged_Lambda([this](const FText& T) { SearchText = T.ToString(); RebuildFilter(); })
		]
		+ SVerticalBox::Slot().AutoHeight().Padding(0, 3)
		[
			SNew(SBox).HeightOverride(230.f)[ClipList.ToSharedRef()]
		]
		+ SVerticalBox::Slot().AutoHeight()
		[
			Wrap({
				Btn(TEXT("Stop / back to game"), [C]() { C->BrowserStop(); }, TEXT("Esc")),
				Btn(TEXT("Motion viewer pedestal"), [C]() { C->ToggleMotionViewerStation(); }, TEXT("M")),
				Toggle(TEXT("loop"), [C]() { return C->GetBrowserLoop(); }, [C](bool B) { C->BrowserSetLoop(B); }),
				Toggle(TEXT("pause"), [this]() { return bPause; }, [this, C](bool B) { bPause = B; if (auto* A = C->GetActions()) A->SetViewerPaused(B); }) })
		]
		+ SVerticalBox::Slot().AutoHeight()[Slide(TEXT("speed 0.5x-1.5x"), 0.5f, 1.5f, [C]() { return C->GetBrowserRate(); }, [C](float V) { C->BrowserSetRate(V); })]
		+ SVerticalBox::Slot().AutoHeight()
		[
			Slide(TEXT("time (scrub)"), 0.f, 1.f,
				[C]() { auto* A = C->GetActions(); return (A && A->GetBaseClipLength() > 0.f) ? A->GetBaseClipTime() / A->GetBaseClipLength() : 0.f; },
				[this, C](float V) { if (auto* A = C->GetActions()) { if (A->IsViewerActive()) { bPause = true; A->SetViewerPaused(true); A->SeekViewer(V * A->GetBaseClipLength()); } } })
		]
		+ SVerticalBox::Slot().AutoHeight().Padding(0, 2)
		[
			SNew(STextBlock).Font(PanelFont(8)).AutoWrapText(true).Text_Lambda([C]() {
				auto* A = C->GetActions();
				if (!A) return FText::GetEmpty();
				return TextOf(FString::Printf(TEXT("playing %s  %.2f / %.2f s   state %s"), *A->GetBaseClipId().ToString(), A->GetBaseClipTime(), A->GetBaseClipLength(), *A->GetStateString()));
			})
		];
}

TSharedRef<SWidget> SShowcasePanel::BuildFaceSection()
{
	AShowcasePlayerController* C = Ctrl.Get();
	TSharedRef<SVerticalBox> Box = SNew(SVerticalBox);
	TArray<TSharedRef<SWidget>> Presets;
	for (const FName& P : UOperativeFaceComponent::GetPresetNames())
	{
		Presets.Add(Btn(P.ToString(), [C, P]() { C->FaceSetPreset(P); }));
	}
	Presets.Add(Btn(TEXT("clear face"), [C]() { C->FaceClear(); }));
	Presets.Add(Btn(TEXT("speech sample"), [C]() { C->CmdDialogue(); }, TEXT("P")));
	Presets.Add(Toggle(TEXT("look at camera"), [C]() { return C->GetLookAtCamera(); }, [C](bool B) { C->SetLookAtCamera(B); }));
	Presets.Add(Toggle(TEXT("auto blink"), [C]() { AOperativeCharacter* O = C->GetOperative(); return O && O->Face && O->Face->GetAutoBlink(); }, [C](bool B) { if (auto* O = C->GetOperative()) O->Face->SetAutoBlink(B); }));
	Box->AddSlot().AutoHeight().Padding(0, 2)[Wrap(Presets)];
	Box->AddSlot().AutoHeight()[Slide(TEXT("clip face weight"), 0.f, 1.f, [C]() { auto* O = C->GetOperative(); return O ? O->Face->GetClipFaceWeight() : 1.f; }, [C](float V) { if (auto* O = C->GetOperative()) O->Face->SetClipFaceWeight(V); })];
	Box->AddSlot().AutoHeight()[Slide(TEXT("jaw open"), 0.f, 1.f, [C]() { auto* O = C->GetOperative(); return O ? O->Face->GetJawOpen() : 0.f; }, [C](float V) { if (auto* O = C->GetOperative()) O->Face->SetJawOpen(V); })];
	Box->AddSlot().AutoHeight()[Slide(TEXT("tongue lift"), 0.f, 1.f, [C]() { auto* O = C->GetOperative(); return O ? O->Face->GetTongueLift() : 0.f; }, [C](float V) { if (auto* O = C->GetOperative()) O->Face->SetTongueLift(V); })];
	Box->AddSlot().AutoHeight()[Slide(TEXT("blink left"), 0.f, 1.f, [C]() { float L = 0, R = 0; if (auto* O = C->GetOperative()) O->Face->GetBlinkSliders(L, R); return L; }, [C](float V) { if (auto* O = C->GetOperative()) { float L, R; O->Face->GetBlinkSliders(L, R); O->Face->SetBlinkSliders(V, R); } })];
	Box->AddSlot().AutoHeight()[Slide(TEXT("blink right"), 0.f, 1.f, [C]() { float L = 0, R = 0; if (auto* O = C->GetOperative()) O->Face->GetBlinkSliders(L, R); return R; }, [C](float V) { if (auto* O = C->GetOperative()) { float L, R; O->Face->GetBlinkSliders(L, R); O->Face->SetBlinkSliders(L, V); } })];
	Box->AddSlot().AutoHeight()[Slide(TEXT("gaze yaw (left +)"), -35.f, 35.f, [C]() { float Y = 0, P = 0; if (auto* O = C->GetOperative()) O->Face->GetManualGaze(Y, P); return Y; }, [C](float V) { if (auto* O = C->GetOperative()) { float Y, P; O->Face->GetManualGaze(Y, P); O->Face->SetManualGaze(V, P); } })];
	Box->AddSlot().AutoHeight()[Slide(TEXT("gaze pitch (up +)"), -25.f, 25.f, [C]() { float Y = 0, P = 0; if (auto* O = C->GetOperative()) O->Face->GetManualGaze(Y, P); return P; }, [C](float V) { if (auto* O = C->GetOperative()) { float Y, P; O->Face->GetManualGaze(Y, P); O->Face->SetManualGaze(Y, V); } })];
	Box->AddSlot().AutoHeight().Padding(0, 4)[SNew(STextBlock).Text(TextOf(TEXT("Visemes (documented mapping in docs/skeleton_and_sockets.json)"))).Font(PanelFont(9)).ColorAndOpacity(FLinearColor(0.7f, 0.9f, 1.f))];
	const UOperativeLibrary* Lib = UOperativeLibrary::Get(C);
	if (Lib)
	{
		for (const FOperativeViseme& V : Lib->GetVisemes())
		{
			const FName N = V.Name;
			Box->AddSlot().AutoHeight()[Slide(FString::Printf(TEXT("%s  (%s)"), *N.ToString(), *V.Phonemes), 0.f, 1.f, [C, N]() { auto* O = C->GetOperative(); return O ? O->Face->GetViseme(N) : 0.f; }, [C, N](float X) { if (auto* O = C->GetOperative()) O->Face->SetViseme(N, X); }, 140)];
		}
		Box->AddSlot().AutoHeight().Padding(0, 4)[SNew(STextBlock).Text(TextOf(TEXT("Individual left / right controls"))).Font(PanelFont(9)).ColorAndOpacity(FLinearColor(0.7f, 0.9f, 1.f))];
		TSet<FString> Done;
		for (const FName& M : Lib->GetMorphNames())
		{
			const FString S = M.ToString();
			FString Base = S;
			bool bPair = false;
			if (S.EndsWith(TEXT("_l")) || S.EndsWith(TEXT("_r")))
			{
				Base = S.LeftChop(2);
				bPair = true;
			}
			if (Done.Contains(Base)) continue;
			Done.Add(Base);
			if (bPair)
			{
				const FName L(*(Base + TEXT("_l"))), R(*(Base + TEXT("_r")));
				Box->AddSlot().AutoHeight()[Slide(Base + TEXT(" L"), 0.f, 1.f, [C, L]() { auto* O = C->GetOperative(); return O ? O->Face->GetMorph(L) : 0.f; }, [C, L](float X) { if (auto* O = C->GetOperative()) O->Face->SetMorph(L, X); }, 140)];
				Box->AddSlot().AutoHeight()[Slide(Base + TEXT(" R"), 0.f, 1.f, [C, R]() { auto* O = C->GetOperative(); return O ? O->Face->GetMorph(R) : 0.f; }, [C, R](float X) { if (auto* O = C->GetOperative()) O->Face->SetMorph(R, X); }, 140)];
			}
			else
			{
				Box->AddSlot().AutoHeight()[Slide(S, 0.f, 1.f, [C, M]() { auto* O = C->GetOperative(); return O ? O->Face->GetMorph(M) : 0.f; }, [C, M](float X) { if (auto* O = C->GetOperative()) O->Face->SetMorph(M, X); }, 140)];
			}
		}
	}
	return Box;
}
