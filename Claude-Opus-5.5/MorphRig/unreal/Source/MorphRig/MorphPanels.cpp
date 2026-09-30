#include "MorphPanels.h"

#include "Framework/Application/SlateApplication.h"
#include "MorphClipLibrary.h"
#include "MorphOperative.h"
#include "MorphShowcaseGameMode.h"
#include "Styling/CoreStyle.h"
#include "Widgets/Input/SButton.h"
#include "Widgets/Input/SCheckBox.h"
#include "Widgets/Input/SSearchBox.h"
#include "Widgets/Input/SSlider.h"
#include "Widgets/Layout/SBorder.h"
#include "Widgets/Layout/SBox.h"
#include "Widgets/Layout/SScrollBox.h"
#include "Widgets/SBoxPanel.h"
#include "Widgets/Text/STextBlock.h"
#include "Widgets/Views/STableRow.h"

namespace
{
	FSlateFontInfo Font(int32 Size, const char* Style = "Regular") { return FCoreStyle::GetDefaultFontStyle(Style, Size); }
	const FSlateBrush* White() { return FCoreStyle::Get().GetBrush("GenericWhiteBox"); }

	// expression presets (same values as the Blender rig presets, mr_face_list.EXPRESSIONS);
	// lid squint / wide / blink and jaw are bone controls (ctl_*), the rest are morph targets
	struct FPresetValue { const TCHAR* Name; float V; };
	const TMap<FString, TArray<FPresetValue>>& Presets()
	{
		static TMap<FString, TArray<FPresetValue>> P;
		if (P.Num() == 0)
		{
			P.Add(TEXT("neutral"), {});
			P.Add(TEXT("joy"), {{TEXT("mouthSmile_L"), 0.85f}, {TEXT("mouthSmile_R"), 0.85f}, {TEXT("cheekRaise_L"), 0.6f},
			                    {TEXT("cheekRaise_R"), 0.6f}, {TEXT("eyeSquint_L"), 0.3f}, {TEXT("eyeSquint_R"), 0.3f},
			                    {TEXT("ctl_squint_l"), 0.25f}, {TEXT("ctl_squint_r"), 0.25f}, {TEXT("browOuterUp_L"), 0.2f},
			                    {TEXT("browOuterUp_R"), 0.2f}, {TEXT("mouthStretch_L"), 0.2f}, {TEXT("mouthStretch_R"), 0.2f},
			                    {TEXT("ctl_jaw_open"), 0.17f}});
			P.Add(TEXT("anger"), {{TEXT("browDown_L"), 0.9f}, {TEXT("browDown_R"), 0.9f}, {TEXT("noseSneer_L"), 0.55f},
			                      {TEXT("noseSneer_R"), 0.55f}, {TEXT("ctl_squint_l"), 0.45f}, {TEXT("ctl_squint_r"), 0.45f},
			                      {TEXT("mouthPress"), 0.45f}, {TEXT("mouthFrown_L"), 0.4f}, {TEXT("mouthFrown_R"), 0.4f},
			                      {TEXT("mouthUpperUp_L"), 0.25f}, {TEXT("mouthUpperUp_R"), 0.25f}, {TEXT("ctl_jaw_open"), 0.06f}});
			P.Add(TEXT("concern"), {{TEXT("browInnerUp_L"), 0.85f}, {TEXT("browInnerUp_R"), 0.85f}, {TEXT("browDown_L"), 0.15f},
			                        {TEXT("browDown_R"), 0.15f}, {TEXT("mouthFrown_L"), 0.45f}, {TEXT("mouthFrown_R"), 0.45f},
			                        {TEXT("mouthStretch_L"), 0.15f}, {TEXT("mouthStretch_R"), 0.15f}, {TEXT("mouthPress"), 0.2f},
			                        {TEXT("ctl_blink_l"), 0.12f}, {TEXT("ctl_blink_r"), 0.12f}, {TEXT("ctl_jaw_open"), 0.08f}});
			P.Add(TEXT("surprise"), {{TEXT("browInnerUp_L"), 0.9f}, {TEXT("browInnerUp_R"), 0.9f}, {TEXT("browOuterUp_L"), 0.9f},
			                         {TEXT("browOuterUp_R"), 0.9f}, {TEXT("ctl_wide_l"), 0.9f}, {TEXT("ctl_wide_r"), 0.9f},
			                         {TEXT("mouthFunnel"), 0.3f}, {TEXT("ctl_jaw_open"), 0.72f}});
			P.Add(TEXT("pain"), {{TEXT("browDown_L"), 0.5f}, {TEXT("browDown_R"), 0.5f}, {TEXT("browInnerUp_L"), 0.7f},
			                     {TEXT("browInnerUp_R"), 0.7f}, {TEXT("ctl_squint_l"), 0.8f}, {TEXT("ctl_squint_r"), 0.8f},
			                     {TEXT("eyeSquint_L"), 0.7f}, {TEXT("eyeSquint_R"), 0.7f}, {TEXT("noseSneer_L"), 0.6f},
			                     {TEXT("noseSneer_R"), 0.6f}, {TEXT("mouthStretch_L"), 0.7f}, {TEXT("mouthStretch_R"), 0.7f},
			                     {TEXT("mouthUpperUp_L"), 0.5f}, {TEXT("mouthUpperUp_R"), 0.5f}, {TEXT("cheekRaise_L"), 0.5f},
			                     {TEXT("cheekRaise_R"), 0.5f}, {TEXT("ctl_jaw_open"), 0.33f}});
			P.Add(TEXT("focus"), {{TEXT("browDown_L"), 0.45f}, {TEXT("browDown_R"), 0.45f}, {TEXT("ctl_squint_l"), 0.35f},
			                      {TEXT("ctl_squint_r"), 0.35f}, {TEXT("eyeSquint_L"), 0.25f}, {TEXT("eyeSquint_R"), 0.25f},
			                      {TEXT("mouthPress"), 0.35f}, {TEXT("mouthRollLower"), 0.1f}});
		}
		return P;
	}
}

// ===================================================================================== browser
void SMorphBrowser::Construct(const FArguments& InArgs)
{
	GM = InArgs._GameMode;
	if (GM.IsValid() && GM->GetLibrary())
	{
		for (const FMorphClip& C : GM->GetLibrary()->All())
		{
			TSharedPtr<FMorphBrowserRow> R = MakeShared<FMorphBrowserRow>();
			R->Id = C.Id;
			R->Form = C.Form;
			R->Duration = C.Duration;
			R->Frames = C.Frames;
			R->Notes = C.Behavior.IsEmpty() ? C.Notes : C.Behavior;
			R->bRequired = C.bRequired;
			R->Markers = C.Markers.Num();
			AllRows.Add(R);
		}
	}
	Rows = AllRows;
	const int32 NumReq = GM.IsValid() && GM->GetLibrary() ? GM->GetLibrary()->NumRequired() : 0;
	ChildSlot
	[
		SNew(SBox).HAlign(HAlign_Right).VAlign(VAlign_Fill).Padding(FMargin(0.f, 70.f, 12.f, 70.f))
		[
			SNew(SBox).WidthOverride(640.f)
			[
				SNew(SBorder).BorderImage(White()).BorderBackgroundColor(FLinearColor(0.02f, 0.025f, 0.03f, 0.88f)).Padding(8.f)
				[
					SNew(SVerticalBox)
					+ SVerticalBox::Slot().AutoHeight().Padding(2.f)
					[
						SNew(STextBlock).Font(Font(12, "Bold")).ColorAndOpacity(FLinearColor(0.2f, 0.85f, 1.f))
						.Text(FText::FromString(FString::Printf(TEXT("ANIMATION BROWSER  (%d inventory entries, %d clips total)  F4 closes"),
						                                         NumReq, AllRows.Num())))
					]
					+ SVerticalBox::Slot().AutoHeight().Padding(2.f)
					[
						SAssignNew(Search, SSearchBox).HintText(FText::FromString(TEXT("search id / form / behaviour...")))
						.OnTextChanged(this, &SMorphBrowser::OnFilter)
					]
					+ SVerticalBox::Slot().AutoHeight().Padding(2.f)
					[
						SNew(SHorizontalBox)
						+ SHorizontalBox::Slot().AutoWidth().Padding(4.f, 0.f)
						[
							SNew(SCheckBox).IsChecked(ECheckBoxState::Checked)
							.OnCheckStateChanged_Lambda([this](ECheckBoxState S) { bLoop = S == ECheckBoxState::Checked; })
							[SNew(STextBlock).Font(Font(9)).Text(FText::FromString(TEXT("loop one-shots in preview")))]
						]
						+ SHorizontalBox::Slot().AutoWidth().Padding(12.f, 0.f)
						[
							SNew(SCheckBox).IsChecked(ECheckBoxState::Unchecked)
							.OnCheckStateChanged_Lambda([this](ECheckBoxState S) {
								bOnlyRequired = S == ECheckBoxState::Checked;
								OnFilter(FText::FromString(Filter));
							})
							[SNew(STextBlock).Font(Font(9)).Text(FText::FromString(TEXT("inventory entries only")))]
						]
						+ SHorizontalBox::Slot().AutoWidth().Padding(12.f, 0.f)
						[
							SNew(SButton).Text(FText::FromString(TEXT("Resume control")))
							.OnClicked_Lambda([this]() {
								if (GM.IsValid() && GM->GetPlayerOperative()) GM->GetPlayerOperative()->CmdResume();
								return FReply::Handled();
							})
						]
					]
					+ SVerticalBox::Slot().FillHeight(1.f).Padding(2.f)
					[
						SAssignNew(List, SListView<TSharedPtr<FMorphBrowserRow>>)
						.ListItemsSource(&Rows)
						.OnGenerateRow(this, &SMorphBrowser::OnRow)
						.SelectionMode(ESelectionMode::Single)
						.OnMouseButtonDoubleClick_Lambda([this](TSharedPtr<FMorphBrowserRow> Item) { Play(Item, false); })
					]
				]
			]
		]
	];
}

void SMorphBrowser::FocusSearch()
{
	if (Search.IsValid())
	{
		FSlateApplication::Get().SetKeyboardFocus(Search, EFocusCause::SetDirectly);
	}
}

void SMorphBrowser::OnFilter(const FText& Text)
{
	Filter = Text.ToString();
	Rows.Reset();
	for (const TSharedPtr<FMorphBrowserRow>& R : AllRows)
	{
		if (bOnlyRequired && !R->bRequired)
		{
			continue;
		}
		if (Filter.IsEmpty() || R->Id.ToString().Contains(Filter) || R->Form.Contains(Filter) || R->Notes.Contains(Filter))
		{
			Rows.Add(R);
		}
	}
	if (List.IsValid())
	{
		List->RequestListRefresh();
	}
}

void SMorphBrowser::Play(TSharedPtr<FMorphBrowserRow> Item, bool bViewer)
{
	if (Item.IsValid() && GM.IsValid())
	{
		GM->PreviewClip(Item->Id, bLoop, bViewer);
	}
}

TSharedRef<ITableRow> SMorphBrowser::OnRow(TSharedPtr<FMorphBrowserRow> Item, const TSharedRef<STableViewBase>& Owner)
{
	const FLinearColor IdCol = Item->bRequired ? FLinearColor(0.9f, 0.95f, 1.f) : FLinearColor(0.6f, 0.65f, 0.7f);
	return SNew(STableRow<TSharedPtr<FMorphBrowserRow>>, Owner).Padding(FMargin(2.f, 1.f))
	[
		SNew(SHorizontalBox)
		+ SHorizontalBox::Slot().FillWidth(0.30f).VAlign(VAlign_Center)
		[SNew(STextBlock).Font(Font(10, "Bold")).ColorAndOpacity(IdCol).Text(FText::FromName(Item->Id))]
		+ SHorizontalBox::Slot().FillWidth(0.20f).VAlign(VAlign_Center)
		[
			SNew(STextBlock).Font(Font(9)).Text(FText::FromString(FString::Printf(TEXT("%s  %df  %.2fs  %dm"), *Item->Form,
			                                                                        Item->Frames, Item->Duration, Item->Markers)))
		]
		+ SHorizontalBox::Slot().FillWidth(0.36f).VAlign(VAlign_Center)
		[SNew(STextBlock).Font(Font(8)).ColorAndOpacity(FLinearColor(0.65f, 0.7f, 0.75f)).Text(FText::FromString(Item->Notes.Left(70)))]
		+ SHorizontalBox::Slot().AutoWidth().Padding(2.f, 0.f)
		[
			SNew(SButton).Text(FText::FromString(TEXT("Play")))
			.OnClicked_Lambda([this, Item]() { Play(Item, false); return FReply::Handled(); })
		]
		+ SHorizontalBox::Slot().AutoWidth().Padding(2.f, 0.f)
		[
			SNew(SButton).Text(FText::FromString(TEXT("Viewer")))
			.OnClicked_Lambda([this, Item]() { Play(Item, true); return FReply::Handled(); })
		]
	];
}

// ===================================================================================== face panel
void SMorphFacePanel::Construct(const FArguments& InArgs)
{
	Op = InArgs._Operative;
	TSharedRef<SScrollBox> Scroll = SNew(SScrollBox);
	auto Header = [&Scroll](const TCHAR* T) {
		Scroll->AddSlot().Padding(2.f, 8.f, 2.f, 2.f)
		[SNew(STextBlock).Font(Font(10, "Bold")).ColorAndOpacity(FLinearColor(0.2f, 0.85f, 1.f)).Text(FText::FromString(T))];
	};
	auto SliderRow = [this, &Scroll](FName Name, bool bControl) {
		Scroll->AddSlot().Padding(2.f, 1.f)
		[
			SNew(SHorizontalBox)
			+ SHorizontalBox::Slot().FillWidth(0.42f).VAlign(VAlign_Center)
			[SNew(STextBlock).Font(Font(9)).Text(FText::FromName(Name))]
			+ SHorizontalBox::Slot().FillWidth(0.58f).VAlign(VAlign_Center)
			[
				SNew(SSlider)
				.Value_Lambda([this, Name, bControl]() {
					return Op.IsValid() ? (bControl ? Op->GetFaceControl(Name) : Op->GetFaceMorph(Name)) : 0.f;
				})
				.OnValueChanged_Lambda([this, Name, bControl](float V) {
					if (!Op.IsValid()) return;
					if (bControl) Op->SetFaceControl(Name, V);
					else Op->SetFaceMorph(Name, V);
				})
			]
		];
	};
	// presets
	TSharedRef<SHorizontalBox> PresetRow = SNew(SHorizontalBox);
	for (const TCHAR* P : {TEXT("neutral"), TEXT("joy"), TEXT("anger"), TEXT("concern"), TEXT("surprise"), TEXT("pain"), TEXT("focus")})
	{
		const FString Name(P);
		PresetRow->AddSlot().AutoWidth().Padding(1.f)
		[
			SNew(SButton).Text(FText::FromString(Name)).OnClicked_Lambda([this, Name]() { ApplyPreset(Name); return FReply::Handled(); })
		];
	}
	Header(TEXT("BONE CONTROLS (lids follow gaze, L / R independent)"));
	for (const FName& N : AMorphOperative::ControlNames())
	{
		SliderRow(N, true);
	}
	Header(TEXT("MORPH TARGETS: brows, eyes, cheeks, nose, mouth (L / R)"));
	for (const FName& N : AMorphOperative::MorphNames())
	{
		if (!N.ToString().StartsWith(TEXT("V_")))
		{
			SliderRow(N, false);
		}
	}
	Header(TEXT("VISEMES (MBP closure, FV labiodental, TH tongue-teeth, AA/EH/EE/IH/OH/OO vowels...)"));
	for (const FName& N : AMorphOperative::MorphNames())
	{
		if (N.ToString().StartsWith(TEXT("V_")))
		{
			SliderRow(N, false);
		}
	}
	ChildSlot
	[
		SNew(SBox).HAlign(HAlign_Left).VAlign(VAlign_Fill).Padding(FMargin(12.f, 110.f, 0.f, 170.f))
		[
			SNew(SBox).WidthOverride(430.f)
			[
				SNew(SBorder).BorderImage(White()).BorderBackgroundColor(FLinearColor(0.02f, 0.025f, 0.03f, 0.88f)).Padding(8.f)
				[
					SNew(SVerticalBox)
					+ SVerticalBox::Slot().AutoHeight()
					[
						SNew(STextBlock).Font(Font(12, "Bold")).ColorAndOpacity(FLinearColor(0.2f, 0.85f, 1.f))
						.Text(FText::FromString(TEXT("FACE CONTROL PANEL  (F3 closes, face camera)")))
					]
					+ SVerticalBox::Slot().AutoHeight().Padding(0.f, 4.f)[PresetRow]
					+ SVerticalBox::Slot().AutoHeight().Padding(0.f, 2.f)
					[
						SNew(SHorizontalBox)
						+ SHorizontalBox::Slot().AutoWidth().Padding(1.f)
						[
							SNew(SButton).Text(FText::FromString(TEXT("Play dialogue (audio)")))
							.OnClicked_Lambda([this]() { if (Op.IsValid()) { Op->ClearFace(); Op->CmdDialogue(); } return FReply::Handled(); })
						]
						+ SHorizontalBox::Slot().AutoWidth().Padding(1.f)
						[
							SNew(SButton).Text(FText::FromString(TEXT("Clear")))
							.OnClicked_Lambda([this]() { if (Op.IsValid()) Op->ClearFace(); return FReply::Handled(); })
						]
					]
					+ SVerticalBox::Slot().FillHeight(1.f)[Scroll]
				]
			]
		]
	];
}

void SMorphFacePanel::ApplyPreset(const FString& Name)
{
	if (!Op.IsValid())
	{
		return;
	}
	Op->ClearFace();
	if (const TArray<FPresetValue>* P = Presets().Find(Name))
	{
		for (const FPresetValue& V : *P)
		{
			const FString S(V.Name);
			if (S.StartsWith(TEXT("ctl_")))
			{
				Op->SetFaceControl(FName(*S), V.V);
			}
			else
			{
				Op->SetFaceMorph(FName(*S), V.V);
			}
		}
	}
}
