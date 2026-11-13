#pragma once
#include "CoreMinimal.h"
#include "Widgets/SCompoundWidget.h"
#include "Widgets/Views/SListView.h"

class AShowcaseDirector;
class UOperativeStateComponent;
class SWidgetSwitcher;
class SVerticalBox;

/** Interactive Slate panel: help, searchable animation browser, face controls, character options, state triggers. */
class SShowcasePanel : public SCompoundWidget
{
public:
	SLATE_BEGIN_ARGS(SShowcasePanel) {}
		SLATE_ARGUMENT(TWeakObjectPtr<UWorld>, World)
	SLATE_END_ARGS()

	void Construct(const FArguments& InArgs);
	void SetTabByName(const FString& Name);

private:
	AShowcaseDirector* Director() const;
	UOperativeStateComponent* State() const;
	void Run(const FString& Command) const;
	TSharedRef<SWidget> Button(const FString& Label, const FString& Command, const FString& Tip = FString());
	TSharedRef<SWidget> ButtonRow(const TArray<TPair<FString, FString>>& Items);
	TSharedRef<SWidget> Header(const FString& Text);
	TSharedRef<SWidget> SliderRow(const FString& Label, TFunction<float()> Getter, TFunction<void(float)> Setter, float Min = 0.f, float Max = 1.f);
	TSharedRef<SWidget> BuildHelp();
	TSharedRef<SWidget> BuildAnimations();
	TSharedRef<SWidget> BuildFace();
	TSharedRef<SWidget> BuildCharacter();
	TSharedRef<SWidget> BuildStates();
	void RefreshClips();
	TSharedRef<ITableRow> MakeClipRow(TSharedPtr<FName> Item, const TSharedRef<STableViewBase>& Owner);

	TWeakObjectPtr<UWorld> World;
	TSharedPtr<SWidgetSwitcher> Switcher;
	TSharedPtr<SListView<TSharedPtr<FName>>> ClipList;
	TArray<TSharedPtr<FName>> ClipItems;
	FString Filter;
	int32 Tab = 0;
};
